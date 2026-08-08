from rest_framework import serializers
from .models import Course, Module, Lesson, AssessmentQuestion, AccessRequest


class LessonSerializer(serializers.ModelSerializer):
    block_tree = serializers.SerializerMethodField()

    class Meta:
        model = Lesson
        fields = '__all__'
        read_only_fields = ['module']

    def get_block_tree(self, instance):
        if instance.type == 'video':
            return None
        from authoring_engine.models import LessonBlockTree
        from authoring_engine.serializers import LessonBlockTreeSerializer
        org = instance.module.course.organization if (instance.module and instance.module.course) else None
        if not org:
            return None
        tree, _ = LessonBlockTree.objects.get_or_create(
            lesson=instance,
            defaults={'organization': org}
        )
        return LessonBlockTreeSerializer(tree, context=self.context).data

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        request = self.context.get('request')
        if ret.get('video_url'):
            if not (ret['video_url'].startswith('http://') or ret['video_url'].startswith('https://')):
                if request is not None:
                    ret['video_url'] = request.build_absolute_uri(ret['video_url'])
                else:
                    ret['video_url'] = request.build_absolute_uri(ret['video_url'])
        return ret

class ModuleSerializer(serializers.ModelSerializer):
    lessons = LessonSerializer(many=True, read_only=True)

    class Meta:
        model = Module
        fields = '__all__'
        read_only_fields = ['course']

class AccessRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = AccessRequest
        fields = '__all__'
        read_only_fields = ['status', 'resolved_at', 'resolved_by', 'requested_at']

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        # Embed standard user details
        if instance.student:
            ret['student_details'] = {
                'id': instance.student.id,
                'full_name': instance.student.full_name,
                'email': instance.student.email
            }
        return ret


class CourseSerializer(serializers.ModelSerializer):
    modules = ModuleSerializer(many=True, read_only=True)
    user_progress = serializers.SerializerMethodField()
    accent = serializers.CharField(required=False, allow_blank=True, default='var(--brand)')

    class Meta:
        model = Course
        fields = '__all__'
        read_only_fields = ['organization']

    def get_user_progress(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return 0
        from .models import LessonProgress, ScormTracking, Lesson

        scorm_pct = 0
        if obj.is_scorm:
            st = ScormTracking.objects.filter(user=request.user, course=obj).first()
            if st:
                if st.lesson_status in ['completed', 'passed']:
                    scorm_pct = 100
                elif st.score_raw is not None and st.score_raw > 0:
                    scorm_pct = min(100, int(st.score_raw))
                elif st.lesson_status in ['incomplete', 'browsed']:
                    scorm_pct = 50

        total_lessons = Lesson.objects.filter(module__course=obj).count()
        lesson_pct = 0
        if total_lessons > 0:
            completed = LessonProgress.objects.filter(user=request.user, lesson__module__course=obj, completed=True).count()
            lesson_pct = int((completed / total_lessons) * 100)

        return max(scorm_pct, lesson_pct)

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        request = self.context.get('request')
        if request:
           if ret.get("hero_url"):
              if not (
                ret["hero_url"].startswith("http://")
                or ret["hero_url"].startswith("https://")
              ):
                ret["hero_url"] = request.build_absolute_uri(ret["hero_url"])
              else:
                    ret['hero_url'] = request.build_absolute_uri(ret["hero_url"])

        if hasattr(instance, 'scorm_package') and instance.scorm_package:
            sp = instance.scorm_package
            launch_url = sp.launch_url
            if launch_url and not (launch_url.startswith('http://') or launch_url.startswith('https://')):
                if request is not None:
                    launch_url = request.build_absolute_uri(launch_url)
            ret['scorm_package'] = {
                'id': sp.id,
                'version': sp.version,
                'schema_version': sp.schema_version,
                'title': sp.title,
                'launch_url': launch_url,
                'mastery_score': sp.mastery_score,
                'sco_structure': sp.sco_structure,
                'uploaded_at': sp.uploaded_at
            }

        return ret


class AssessmentQuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssessmentQuestion
        fields = '__all__'

from .models import AssessmentAttempt
class AssessmentAttemptSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssessmentAttempt
        fields = '__all__'
from .models import IssuedCertificate

class IssuedCertificateSerializer(serializers.ModelSerializer):
    course_title = serializers.CharField(source='course.title', read_only=True)
    user_name = serializers.SerializerMethodField()
    organization_name = serializers.SerializerMethodField()
    certificate_template_html = serializers.SerializerMethodField()

    class Meta:
        model = IssuedCertificate
        fields = ['id', 'certificate_id', 'course', 'course_title', 'user_name', 'organization_name', 'issued_at', 'certificate_template_html']

    def get_user_name(self, obj):
        if obj.user:
            return obj.user.full_name or f"{obj.user.first_name} {obj.user.last_name}".strip() or obj.user.username
        return "Learner"

    def get_organization_name(self, obj):
        if obj.user and obj.user.organization:
            return obj.user.organization.name
        return "Learning Platform"

    def get_certificate_template_html(self, obj):
        if obj.template_html_snapshot:
            return obj.template_html_snapshot
        if obj.template:
            return obj.template.body_html
        if obj.user and obj.user.organization:
            from organizations.models import CertificateTemplate
            tpl = CertificateTemplate.objects.filter(organization=obj.user.organization).first()
            if tpl:
                return tpl.body_html
        return None

from .models import LearningPath, LearningPathCourse, LessonProgress, ScormTracking

class LearningPathCourseSerializer(serializers.ModelSerializer):
    course = CourseSerializer(read_only=True)
    course_id = serializers.PrimaryKeyRelatedField(
        queryset=Course.objects.all(), source='course', write_only=True
    )

    class Meta:
        model = LearningPathCourse
        fields = ['id', 'course', 'course_id', 'order']

class LearningPathSerializer(serializers.ModelSerializer):
    path_courses = LearningPathCourseSerializer(many=True, read_only=True)
    course_ids = serializers.ListField(
        child=serializers.IntegerField(), write_only=True, required=False
    )
    total_courses = serializers.SerializerMethodField()
    total_duration_hrs = serializers.SerializerMethodField()
    progress_pct = serializers.SerializerMethodField()
    is_completed = serializers.SerializerMethodField()

    class Meta:
        model = LearningPath
        fields = [
            'id', 'title', 'description', 'created_at', 'path_courses', 
            'course_ids', 'total_courses', 'total_duration_hrs', 'progress_pct', 'is_completed'
        ]
        read_only_fields = ['organization']

    def get_total_courses(self, obj):
        return obj.path_courses.count()

    def get_total_duration_hrs(self, obj):
        total = 0.0
        for pc in obj.path_courses.select_related('course').all():
            if pc.course and pc.course.duration_hrs:
                total += float(pc.course.duration_hrs)
        return round(total, 1)

    def get_progress_pct(self, obj):
        request = self.context.get('request')
        if not request or not request.user or not request.user.is_authenticated:
            return 0

        path_courses_list = list(obj.path_courses.select_related('course').all())
        if not path_courses_list:
            return 0

        total_progress = 0
        for pc in path_courses_list:
            course = pc.course
            if not course:
                continue

            total_lessons = Lesson.objects.filter(module__course=course).count()
            scorm_pct = 0
            if course.is_scorm:
                st = ScormTracking.objects.filter(user=request.user, course=course).first()
                if st:
                    if st.lesson_status in ['completed', 'passed']:
                        scorm_pct = 100
                    elif st.score_raw is not None and st.score_raw > 0:
                        scorm_pct = min(100, int(st.score_raw))
                    elif st.lesson_status in ['incomplete', 'browsed']:
                        scorm_pct = 50

            lesson_pct = 0
            if total_lessons > 0:
                completed = LessonProgress.objects.filter(user=request.user, lesson__module__course=course, completed=True).count()
                lesson_pct = int((completed / total_lessons) * 100)

            total_progress += max(scorm_pct, lesson_pct)

        return int(total_progress / len(path_courses_list))

    def get_is_completed(self, obj):
        return self.get_progress_pct(obj) == 100

    def create(self, validated_data):
        course_ids = validated_data.pop('course_ids', None)
        path = LearningPath.objects.create(**validated_data)
        if course_ids:
            self._save_courses(path, course_ids)
        return path

    def update(self, instance, validated_data):
        course_ids = validated_data.pop('course_ids', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if course_ids is not None:
            self._save_courses(instance, course_ids)
        return instance

    def _save_courses(self, path, course_ids):
        path.path_courses.all().delete()
        new_links = []
        for order, cid in enumerate(course_ids):
            try:
                c = Course.objects.get(pk=cid)
                new_links.append(LearningPathCourse(learning_path=path, course=c, order=order))
            except Course.DoesNotExist:
                pass
        LearningPathCourse.objects.bulk_create(new_links)

from .models import ScormPackage, ScormTracking

class ScormPackageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScormPackage
        fields = '__all__'

class ScormTrackingSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScormTracking
        fields = '__all__'

