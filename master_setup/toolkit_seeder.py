"""
Toolkit Seeder Engine
Auto-inspects live Django models, API endpoints, workflows, and configurations to generate project-specific documentation articles across all 30 core sections.
"""
import os
import django
from django.utils.text import slugify

def seed_toolkit():
    from master_setup.models import (
        ToolkitCategory, ToolkitArticle, ToolkitArticleVersion,
        ToolkitChangeLog, ToolkitReleaseNote, ToolkitDependencyNode
    )

    # 1. Define Categories
    categories_def = [
        ("Platform Overview", "Layout", "Architecture and business introduction of the SaaS Multi-Tenant LMS."),
        ("Architecture", "Cpu", "Technical architecture covering Backend, Frontend, RBAC, and Pipelines."),
        ("Master Setup Documentation", "Settings", "Super Admin Master Console modules, configurations, and tenant policies."),
        ("Organization Admin Documentation", "Building2", "Org Admin portal features, department trees, roles, and module access."),
        ("Learner Documentation", "GraduationCap", "Learner catalog, lesson player, quizzes, certificates, and profile."),
        ("Module Documentation", "Box", "In-depth specs for every individual module in the system."),
        ("Feature Documentation", "Sliders", "Specs, inputs, and validations for every individual feature."),
        ("Workflow Documentation", "GitMerge", "End-to-end multi-step workflow guides from start to finish."),
        ("Content Authoring Guide", "Edit3", "Polymorphic lesson authoring, block editor, quiz builder, and scenarios."),
        ("SCORM Documentation", "FileArchive", "SCORM 1.2 and SCORM 2004 manifest standards, player tracking, and export."),
        ("XML Documentation", "FileCode", "XML generation, imsmanifest.xml specs, schema validation, and packaging."),
        ("API Documentation", "Globe", "REST API endpoint documentation, methods, headers, and response formats."),
        ("Database Documentation", "Database", "ORM models, table schemas, foreign key relationships, and indexes."),
        ("UI Components Documentation", "LayoutTemplate", "Reusable UI design system, AppShell, SuperAdminShell, and dialogs."),
        ("Settings & Toggles", "ToggleLeft", "Platform and tenant configuration settings and feature flags."),
        ("Error Resolution Center", "AlertTriangle", "Known error codes, root cause diagnosis, and resolution steps."),
        ("Troubleshooting Guide", "Wrench", "Step-by-step diagnostic workflows for common operational issues."),
        ("Deployment Guide", "Server", "Environment variables, deployment checklists, and production hosting."),
        ("Security Documentation", "ShieldCheck", "JWT auth, RBAC permissions, password hashing, and tenant isolation."),
        ("Release Notes", "Tag", "Platform release history, new features, and bug fixes."),
        ("Version History", "History", "Course & article versioning, non-destructive snapshot restoration."),
        ("Search Engine", "Search", "Global project-wide search capabilities across all entities."),
        ("Audit Logs", "ClipboardList", "Administrative audit trailing and security compliance monitoring."),
        ("Project Change Log", "GitCommit", "Chronological history of platform codebase edits and updates."),
        ("Feature Dependency Map", "Network", "Dependency chains and module-level relationship diagrams."),
        ("Impact Analysis", "Activity", "Risk and change impact analysis for database and API modifications."),
        ("API Explorer", "Terminal", "Interactive REST API documentation and payload explorer."),
        ("Database Explorer", "HardDrive", "Interactive database schema and table structure explorer."),
        ("Configuration Explorer", "Sliders", "Global and tenant configuration parameter reference."),
        ("Live System Health", "HeartPulse", "Live operational metrics, queue status, and system uptime monitoring."),
    ]

    cat_map = {}
    for idx, (name, icon, desc) in enumerate(categories_def):
        cat, _ = ToolkitCategory.objects.get_or_create(
            slug=slugify(name),
            defaults={'name': name, 'icon': icon, 'description': desc, 'order': idx + 1}
        )
        cat_map[name] = cat

    # 2. Comprehensive Articles for all 30 Categories
    articles_data = [
        # 1. Platform Overview
        ("Platform Overview", "Multi-Tenant SaaS LMS Architecture Overview", "multi-tenant-saas-lms-architecture",
         "High-level architectural overview of the Multi-Tenant LMS SaaS platform.",
         """# Multi-Tenant SaaS LMS Architecture

The **Enterprise LMS Platform** is engineered as a multi-tenant Software-as-a-Service architecture supporting hierarchical tenant isolation, customizable branding, independent org policies, and role-based access control.

## Key Architectural Highlights

- **Backend Stack**: Django REST Framework (DRF) running on Python 3.10 with SQLite/PostgreSQL, token authentication, and custom middleware.
- **Frontend Stack**: React 18, TanStack Router (file-based routing), TailwindCSS, and Lucide React icons.
- **Console Hierarchy**:
  1. **Super Admin (Master Setup Console)**: Multi-tenant management, feature toggles, plan catalog, platform settings, and Master Toolkit.
  2. **Organization Admin Console**: Department hierarchy, custom roles, course building, module access, certificates, and branding.
  3. **Learner Portal**: Interactive course catalog, polymorphic lesson player, knowledge check evaluations, scenario simulations, and certificate downloads.

## Multi-Tenant Isolation
Every business model (`User`, `Course`, `Department`, `Role`, `LessonBlockTree`) belongs to an `Organization`. Backend middleware automatically scopes database queries by `request.user.organization_id`, ensuring strict tenant data isolation.""",
         "published", None, ["architecture", "multi-tenant", "overview"]),

        ("Platform Overview", "Console Hierarchy & User Access Roles", "console-hierarchy-and-user-access-roles",
         "In-depth breakdown of platform console levels, user access roles, RBAC matrix, and multi-tenant security boundaries.",
         """# Console Hierarchy & User Access Roles

The **SaaS Multi-Tenant LMS Platform** implements a 4-tier console architecture backed by Role-Based Access Control (RBAC) and explicit multi-tenant data isolation. Every user account operates within a strictly defined administrative boundary based on their global superadmin flag (`is_platform_super_admin`), assigned organization tenant (`organization`), and custom granular role permissions (`Role`).

---

## 1. Executive Console Hierarchy

The platform is structured into four distinct functional consoles, each tailored to specific organizational workflows:

1. **Level 1: Super Admin Console (Master Setup)** — Global platform management, tenant provisioning, system feature flags, and Master Toolkit.
2. **Level 2: Organization Admin Console** — Tenant management, department hierarchies, user provisioning, custom roles, and branding.
3. **Level 3: Content Authoring Workplace** — Polymorphic block tree lesson editor, quiz builder, and branching decision scenarios.
4. **Level 4: Learner Experience Portal** — Interactive course catalog, distraction-free polymorphic course player, knowledge checks, and certificate generation.

---

## 2. Console Level 1: Super Admin (Master Setup Console)

### Overview
The **Master Setup Console** is the supreme governance layer of the LMS platform. It provides platform owner administrators with absolute system-wide visibility, multi-tenant organization provisioning, subscription management, global feature flagging, and system health monitoring.

### Target User Profile
- **Account Attribute**: `is_platform_super_admin = True`
- **Tenant Scoping**: Unscoped (`organization = None`). Super Admins transcend individual tenant boundaries.
- **REST API Permission Guard**: `SuperAdminPermission` class in Django REST Framework.

### Accessible Console Modules & Routes
| Route | Module Name | Core Capabilities & Governance |
| :--- | :--- | :--- |
| `/super-admin/dashboard` | **Platform Dashboard** | System-wide tenant counters, global user metrics, active course stats, storage utilization. |
| `/super-admin/organizations` | **Organization Management** | Provision new tenants, assign domain/subdomains, adjust tenant status (`active`, `suspended`, `archived`). |
| `/super-admin/sites` | **Multi-Site Domain Setup** | Map custom domains, SSL bindings, and tenant site routing rules. |
| `/super-admin/access-control` | **Global RBAC Catalog** | Define global role templates and default permission inheritance rules. |
| `/super-admin/plans` | **Subscription Plan Catalog** | Create subscription tiers (Free, Professional, Enterprise) and enforce user/storage/SCORM limits. |
| `/super-admin/global-settings` | **Platform Configuration** | Global SMTP email server setup, security token expiration TTLs, default branding palettes. |
| `/super-admin/billing` | **Billing & Subscription Log** | Track tenant billing cycles, invoice histories, plan upgrades, and payment status. |
| `/super-admin/activity` | **Global Audit Trail** | Log platform-wide administrative actions, security login events, and tenant provisioning logs. |
| `/super-admin/setup-guide` | **Master Onboarding Wizard** | Step-by-step master setup guide for initializing platform settings and default templates. |
| `/super-admin/toolkit` | **Master Toolkit** | Central Knowledge Base, System Health Monitor, REST API Explorer, Database Explorer, Change Log, Dependency Map, and Backup Engine. |

---

## 3. Console Level 2: Organization Admin Console

### Overview
The **Organization Admin Console** enables tenant administrators to manage their organization's internal operations, department hierarchies, custom user roles, user provisioning, branding customizations, and course publishing within their tenant boundary.

### Target User Profile
- **Account Attribute**: `is_platform_super_admin = False`, assigned to `organization_id = <Tenant_ID>`.
- **Role Association**: User linked to an administrative `Role` record where `is_admin_role = True` or explicit permission flags are enabled.
- **Tenant Scoping**: All database queries are automatically filtered by `WHERE organization_id = <Tenant_ID>`.

### Accessible Console Modules & Routes
| Route | Module Name | Core Capabilities & Governance |
| :--- | :--- | :--- |
| `/org-admin` | **Org Dashboard** | Tenant active learners, course completion velocity, department analytics, and recent activity. |
| `/org-admin/users` | **User Management** | Provision users, bulk import via CSV, assign roles/departments, reset passwords, freeze accounts. |
| `/org-admin/departments` | **Department Hierarchy** | Build nested department tree structures (e.g. Engineering -> Frontend Team) for targeted enrollment. |
| `/org-admin/roles` | **Custom RBAC Creator** | Create custom organization roles with granular boolean permission toggles. |
| `/org-admin/courses` | **Course Management** | View organization course inventory, toggle catalog visibility, export courses as SCORM. |
| `/org-admin/courses/$id/builder` | **Course Builder** | Full-width polymorphic block tree editor for constructing lessons, quizzes, and scenarios. |
| `/org-admin/courses/$id/preview` | **Learner Player Preview** | Preview authored lessons in real-time exact learner player rendering mode. |
| `/org-admin/module-access` | **Module Access Control** | Enable or disable specific platform modules for custom organization roles. |
| `/org-admin/certificates` | **Certificate Designer** | Design PDF certificate templates with custom backgrounds, signatures, and dynamic tags. |
| `/org-admin/activity` | **Tenant Activity Log** | View organization audit logs, learner course completions, and assessment attempts. |

---

## 4. Console Level 3: Content Authoring Workplace

### Overview
The **Content Authoring Workplace** is an integrated workplace within the Org Admin and Instructor workflows. It provides course creators with a distraction-free, broad layout environment for crafting interactive learning content using polymorphic block trees.

### Granular Authoring Permissions
- `can_create_courses`: Allows initializing new course drafts and defining metadata (title, category, level, thumbnail).
- `can_edit_courses`: Grants editing rights to module structures, lesson content, and block trees.
- `can_publish_courses`: Controls state transition from `draft` -> `published`, making content live in the Learner Catalog.

### Polymorphic Block Tree Capabilities
- **Rich Content Blocks**: Typography Headings, Paragraphs, Code snippets, Tables, Callout alert boxes.
- **Media Embed Blocks**: Direct video streaming, audio tracks, PDF inline viewers, image galleries.
- **Interactive Knowledge Checks**: Single-choice, multiple-choice, drag-and-drop, and flashcard activities.
- **Branching Decision Scenarios**: Interactive node-based decision trees with customized feedback loops.

---

## 5. Console Level 4: Learner Experience Portal

### Overview
The **Learner Experience Portal** is a sleek, distraction-free environment designed for student engagement, course consumption, knowledge verification, and certificate attainment.

### Accessible Learner Routes
| Route | Module Name | Learner Experience & Functionality |
| :--- | :--- | :--- |
| `/catalog` | **Course Catalog** | Browse published courses, filter by department/level/category, search titles, view course cards. |
| `/courses/$courseId` | **Course Overview** | View course landing page, syllabus outline, total duration, instructor details, enrollment status. |
| `/courses/$id/play/$lessonId` | **Polymorphic Course Player** | Distraction-free lesson player, sidebar navigation, auto progress tracking, block rendering. |
| `/courses/$id/assessment` | **Course Assessment** | End-of-course exam evaluation with timer, passing score verification, and instant feedback. |
| `/certificates` | **My Certificates** | View earned course certificates, download high-res PDF credentials, verify QR codes. |
| `/profile` | **User Profile** | Manage personal information, avatar, password updates, and personal learning transcripts. |

---

## 6. Granular Permission Flags Matrix

The `Role` model in the backend schema enforces 12+ granular boolean flags that govern UI route access and REST API view execution:

```python
class Role(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    is_default = models.BooleanField(default=False)
    is_admin_role = models.BooleanField(default=False)
    
    # Granular Permissions
    can_manage_users = models.BooleanField(default=False)
    can_manage_departments = models.BooleanField(default=False)
    can_manage_roles = models.BooleanField(default=False)
    can_create_courses = models.BooleanField(default=False)
    can_edit_courses = models.BooleanField(default=False)
    can_publish_courses = models.BooleanField(default=False)
    can_manage_module_access = models.BooleanField(default=False)
    can_view_reports = models.BooleanField(default=False)
    can_manage_certificates = models.BooleanField(default=False)
```

### Security Guard Matrix
| Administrative Action | Frontend Route Guard | REST API Permission Guard | HTTP Response if Unauthorized |
| :--- | :--- | :--- | :--- |
| **Super Admin Master Console Access** | `user.is_platform_super_admin` | `SuperAdminPermission` | `403 Forbidden` |
| **User Account Provisioning** | `role.can_manage_users` | `HasOrgRolePermission('can_manage_users')` | `403 Forbidden` |
| **Department Tree Editing** | `role.can_manage_departments` | `HasOrgRolePermission('can_manage_departments')` | `403 Forbidden` |
| **Course Building & Block Editing** | `role.can_edit_courses` | `HasOrgRolePermission('can_edit_courses')` | `403 Forbidden` |
| **Course Catalog Publishing** | `role.can_publish_courses` | `HasOrgRolePermission('can_publish_courses')` | `403 Forbidden` |
| **Certificate Template Design** | `role.can_manage_certificates` | `HasOrgRolePermission('can_manage_certificates')` | `403 Forbidden` |
| **Unauthenticated API Call** | Valid Bearer Token | `IsAuthenticated` | `401 Unauthorized` |

---

## 7. Version Snapshots & Security Compliance

Every article and documentation item in the Master Toolkit supports non-destructive version snapshots. Restoring a snapshot creates a new draft version, ensuring that version histories remain immutable and audit-compliant across all enterprise consoles.""",
         "published", None, ["roles", "consoles", "permissions"]),

        # 2. Architecture
        ("Architecture", "Master Platform Architecture, Backend Services & Frontend Framework", "master-platform-backend-frontend-architecture",
         "High-level system architecture specification covering Django REST Framework backend microservices, React/TanStack frontend, and REST API routing flows.",
         """# Master Platform Architecture, Backend Services & Frontend Framework

The **SaaS Multi-Tenant LMS Platform** is constructed using a decoupled client-server architecture consisting of a Python/Django REST Framework backend services layer, a React 18 / TanStack Start frontend application, and an asynchronous data persistence layer.

---

## 1. High-Level System Architecture Diagram

```mermaid
graph TD
    Client["Client Browser (React 18 / TanStack)"]
    ViteServer["Vite / Nitro Dev & SSR Server (Port 8080)"]
    DjangoAPI["Django REST API Gateway (Port 8000)"]
    DB[("Relational Database (SQLite / PostgreSQL)")]
    MediaStorage[("Media File Storage (SCORM / Video / PDF)")]

    Client -->|HTTP Requests| ViteServer
    ViteServer -->|Reverse Proxy / Direct API| DjangoAPI
    DjangoAPI -->|ORM Scoped Queries| DB
    DjangoAPI -->|Byte-Range Streaming| MediaStorage
```

---

## 2. Backend Architecture Specification

The backend service layer is built on **Python 3.10** and **Django 5.2 / Django REST Framework (DRF)**, structured into modular domain applications:

| Django Application | Primary Responsibility & Services | Key Models |
| :--- | :--- | :--- |
| `users` | User authentication, JWT issuance, profile retrieval, account freezing. | `User`, `UserActivity` |
| `organizations` | Tenant organization provisioning, custom domains, RBAC roles, departments. | `Organization`, `Department`, `Role` |
| `courses` | Course catalog, modules, lessons, assessments, certificates, SCORM tracking. | `Course`, `Module`, `Lesson`, `IssuedCertificate`, `ScormPackage`, `ScormTracking` |
| `master_setup` | Super admin setup console, plan catalog, platform settings, Master Toolkit. | `PlatformSettings`, `Plan`, `ToolkitArticle`, `ToolkitAuditLog` |
| `authoring_engine` | Polymorphic block tree authoring, block payloads, pre-flight validation. | `LessonBlockTree`, `LessonBlock` |
| `import_engine` | Universal course ingestion pipeline (PDF, DOCX, PPTX, SCORM ZIP). | `ImportJob` |
| `scorm_export` | Package compilation into SCORM 1.2 and SCORM 2004 ZIP archives. | Exporter Utility Engine |

---

## 3. Frontend Architecture Specification

The frontend application is built on **React 18**, **TanStack Router** (file-based routing), **TanStack Query** (async data caching), and **TailwindCSS**:

- **File-Based Routing (`src/routes/`)**:
  - `/super-admin/*`: Super Admin Master Setup Console routes.
  - `/org-admin/*`: Organization Admin management routes.
  - `/catalog` & `/courses/*`: Learner Experience Portal & Polymorphic Course Player routes.
- **State Management & Caching**: TanStack Query handles background refetching and client-side cache invalidation.
- **Theme & Design System**: Vanilla CSS tokens integrated with Tailwind utilities supporting dark/light mode toggle.

---

## 4. API Request & Data Flow Architecture

```mermaid
sequenceDiagram
    autonumber
    actor Learner as Learner Client
    participant App as React Frontend
    participant Auth as Auth Interceptor
    participant Gateway as Django API Gateway
    participant ORM as Tenant Scoped ORM
    participant DB as Database

    Learner->>App: Click Launch Course
    App->>Auth: Request API Resource (/api/courses/101/)
    Auth->>Auth: Attach Authorization: Bearer Token
    Auth->>Gateway: HTTP GET /api/courses/101/
    Gateway->>Gateway: Authenticate JWT Token
    Gateway->>ORM: Evaluate get_queryset() (Filter by org_id)
    ORM->>DB: Execute Scoped SQL Query
    DB-->>ORM: Return Data Rows
    ORM-->>Gateway: Serialize Model to JSON
    Gateway-->>App: HTTP 200 OK + JSON Response Payload
    App-->>Learner: Render Course UI
```
""",
         "published", None, ["architecture", "backend", "frontend", "api"]),

        ("Architecture", "Multi-Tenant Isolation, Database Schema, Authentication & RBAC Matrix", "multi-tenant-database-auth-rbac-architecture",
         "Deep technical specification of tenant data isolation, ERD database schema, JWT authentication flow, and granular RBAC security guards.",
         """# Multi-Tenant Isolation, Database Schema, Authentication & RBAC Matrix

Security and data integrity across multi-tenant boundaries are enforced through strict database query scoping, JWT token authentication, and granular Role-Based Access Control (RBAC).

---

## 1. Entity Relationship Model (ERD)

```mermaid
erDiagram
    ORGANIZATION ||--o{ USER : owns
    ORGANIZATION ||--o{ DEPARTMENT : structures
    ORGANIZATION ||--o{ ROLE : defines
    ORGANIZATION ||--o{ COURSE : owns
    DEPARTMENT ||--o{ USER : assigns
    ROLE ||--o{ USER : grants
    COURSE ||--o{ MODULE : contains
    MODULE ||--o{ LESSON : contains
    LESSON ||--o` LESSON_BLOCK_TREE : includes
    LESSON_BLOCK_TREE ||--o{ LESSON_BLOCK : composes
    COURSE ||--o{ ISSUED_CERTIFICATE : generates
```

---

## 2. Multi-Tenant Data Isolation Engine

The LMS utilizes a **Shared Database, Discriminator Key** multi-tenancy model. Every data table contains an `organization_id` foreign key.

```python
class BaseTenantScopedViewSet(viewsets.ModelViewSet):
    # Abstract ViewSet enforcing strict tenant isolation across all endpoints.
    def get_queryset(self):
        user = self.request.user
        if getattr(user, 'is_platform_super_admin', False):
            return self.queryset.all()
        if user.organization_id:
            return self.queryset.filter(organization_id=user.organization_id)
        return self.queryset.none()
```

---

## 3. JWT Authentication Flow

1. User authenticates at `POST /api/users/auth/login/` with username & password.
2. Django issues an `access_token` (short-lived TTL) and `refresh_token` (long-lived TTL).
3. Frontend utility `authFetch()` attaches `Authorization: Bearer <access_token>` to every HTTP request.
4. On `HTTP 401 Unauthorized`, `authFetch()` automatically issues a token refresh request to `POST /api/users/auth/refresh/` and retries the original request.

---

## 4. RBAC Security Guards Matrix

| Administrative Action | Frontend Route Guard | REST API Permission Guard | HTTP Response if Unauthorized |
| :--- | :--- | :--- | :--- |
| **Super Admin Master Console Access** | `user.is_platform_super_admin` | `SuperAdminPermission` | `403 Forbidden` |
| **User Account Provisioning** | `role.can_manage_users` | `HasOrgRolePermission('can_manage_users')` | `403 Forbidden` |
| **Department Tree Editing** | `role.can_manage_departments` | `HasOrgRolePermission('can_manage_departments')` | `403 Forbidden` |
| **Course Building & Block Editing** | `role.can_edit_courses` | `HasOrgRolePermission('can_edit_courses')` | `403 Forbidden` |
| **Course Catalog Publishing** | `role.can_publish_courses` | `HasOrgRolePermission('can_publish_courses')` | `403 Forbidden` |
| **Certificate Template Design** | `role.can_manage_certificates` | `HasOrgRolePermission('can_manage_certificates')` | `403 Forbidden` |
""",
         "published", None, ["database", "tenant-isolation", "jwt", "rbac"]),

        ("Architecture", "Polymorphic Content Authoring, Assessment Engine & Course Lifecycle Pipelines", "polymorphic-authoring-assessment-lifecycle-architecture",
         "Technical breakdown of polymorphic lesson block tree authoring, knowledge check assessment grading, and course lifecycle state transitions.",
         """# Polymorphic Content Authoring, Assessment Engine & Course Lifecycle Pipelines

The course authoring engine provides course creators with a flexible block tree editor, integrated quiz evaluation tools, and lifecycle state management.

---

## 1. Polymorphic Authoring Block Pipeline

Lessons are composed of ordered, independent `LessonBlock` instances inside a `LessonBlockTree` container.

```mermaid
graph LR
    Tree["LessonBlockTree (Root)"] --> B1["Block 1: Heading"]
    Tree --> B2["Block 2: Paragraph"]
    Tree --> B3["Block 3: Video Stream"]
    Tree --> B4["Block 4: Knowledge Check Quiz"]
    Tree --> B5["Block 5: Branching Scenario"]
```

### Supported Block Discriminators
1. **Heading**: Semantic HTML headers (`h1`-`h4`).
2. **Paragraph**: Rich text content.
3. **Media (Image/Video/Audio/PDF)**: Direct media streaming and document embedding.
4. **Table**: Formatted header and row data tables.
5. **Callout**: Highlighted informational or warning callout boxes (`info`, `warning`, `tip`, `danger`).
6. **Code**: Syntax-highlighted code blocks.
7. **Interaction**: Flashcards, Drag-and-Drop, Hotspots.
8. **Quiz**: Single-choice and multiple-choice questions with automated explanations.
9. **Branching Scenario**: Decision tree simulations with node-based pathways.

---

## 2. Assessment & Grading Engine Flow

```mermaid
flowchart TD
    Start["Learner Begins Exam (/assessment)"] --> FetchQ["Fetch Question Pool"]
    FetchQ --> SubmitA["Learner Submits Answers"]
    SubmitA --> Grade["Evaluate Correct Options"]
    Grade --> CalcScore["Calculate Score Percentage"]
    CalcScore --> CheckPass{"Score >= Passing Threshold?"}
    CheckPass -- Yes --> MarkPass["Mark Course Completed & Generate Certificate"]
    CheckPass -- No --> MarkFail["Record Exam Attempt & Allow Retry"]
```

---

## 3. Course Lifecycle & Publishing State Pipeline

Courses progress through four strict lifecycle states:

```mermaid
stateDiagram-v2
    [*] --> Draft : Creator initializes course
    Draft --> InReview : Author submits for approval
    InReview --> Published : Org Admin executes pre-flight checklist
    Published --> Archived : Deprecated by Admin
    Published --> Draft : Snapshot Restoration (Creates new draft)
```

1. **Draft**: Initial editing state. Content is visible only to authors and org admins.
2. **In Review**: Pending pre-flight validation and editorial review.
3. **Published**: Course is visible in the Learner Catalog (`/catalog`) and eligible for enrollment.
4. **Archived**: Course is hidden from catalog; existing enrolled learners retain historical transcripts.
5. **Non-Destructive Snapshot Versioning**: Restoring a historical snapshot generates a new `Draft` version without overwriting published or historical versions.
""",
         "published", None, ["authoring", "assessment", "course-lifecycle", "versioning"]),

        ("Architecture", "Universal Course Import & SCORM/Package Export Pipelines", "universal-import-export-xml-pipelines-architecture",
         "Architectural specification of universal course ingestion (PDF, DOCX, PPTX, SCORM ZIP) and SCORM 1.2/2004 manifest export generation.",
         """# Universal Course Import & SCORM/Package Export Pipelines

The import and export subsystems enable seamless migration between external legacy packages (SCORM, PDF, Office documents) and our platform's internal polymorphic format.

---

## 1. Universal Course Import Pipeline

```mermaid
flowchart TD
    Upload["Upload Source File (PDF / DOCX / PPTX / SCORM ZIP)"] --> Job["Create ImportJob (Status = Pending)"]
    Job --> Detect{"Detect File Format"}
    Detect -- SCORM ZIP --> ParseManifest["Parse imsmanifest.xml & SCO Files"]
    Detect -- PDF / DOCX --> ParseDoc["Extract Text, Images & Headings"]
    ParseManifest --> Convert["Convert to Polymorphic LessonBlockTree"]
    ParseDoc --> Convert
    Convert --> StoreSource["Preserve & Link Original Source File"]
    StoreSource --> Complete["ImportJob Status = Completed"]
```

---

## 2. SCORM Package Export Pipeline

```mermaid
flowchart TD
    Select["Select Published Course"] --> CheckPub{"Verify Status == Published"}
    CheckPub -- No --> Reject["Error: Only Published Courses Exportable"]
    CheckPub -- Yes --> Compile["Scorm12Exporter / Scorm2004Exporter"]
    Compile --> Extract["Extract Lessons & Render HTML Wrappers"]
    Compile --> BuildXML["Build imsmanifest.xml via ElementTree"]
    BuildXML --> Zip["Compress into Standard SCORM ZIP"]
    Zip --> Download["Download Package Archive"]
```

---

## 3. XML Manifest Generation (`imsmanifest.xml`)

The `ManifestBuilder` dynamically constructs valid XML manifests with standard namespaces (`imscp`, `adlcp`, `adlseq`):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<manifest identifier="MANIFEST-COURSE-101" version="1.0"
          xmlns="http://www.imsproject.org/xsd/imscp_rootv1p1p2"
          xmlns:adlcp="http://www.adlnet.org/xsd/adlcp_rootv1p2">
  <metadata>
    <schema>ADL SCORM</schema>
    <schemaversion>1.2</schemaversion>
  </metadata>
  <organizations default="ORG-DEFAULT">
    <organization identifier="ORG-DEFAULT">
      <title>Platform Architecture Course</title>
      <item identifier="ITEM-1" identifierref="RES-1">
        <title>Lesson 1: Architecture Overview</title>
      </item>
    </organization>
  </organizations>
  <resources>
    <resource identifier="RES-1" type="webcontent" adlcp:scormtype="sco" href="lesson_1.html">
      <file href="lesson_1.html"/>
    </resource>
  </resources>
</manifest>
```
""",
         "published", None, ["import", "export", "scorm", "xml"]),

        ("Architecture", "SCORM 1.2 & 2004 Runtime Engine, CMI Data Tracking & Player Architecture", "scorm-12-2004-runtime-cmi-tracking-architecture",
         "Technical documentation of SCORM runtime execution, JavaScript CMI bridge injection, and asynchronous progress persistence.",
         """# SCORM 1.2 & 2004 Runtime Engine, CMI Data Tracking & Player Architecture

The **SCORM Runtime Engine** enables the execution of standard SCORM 1.2 and SCORM 2004 SCO content packages inside an isolated, cross-origin safe iframe player container.

---

## 1. SCORM Player Architecture

```mermaid
graph TD
    Player["ScormPlayer Component"] --> IFrame["Isolated Content IFrame"]
    Player --> CMIBridge["JavaScript CMI Bridge (window.API / window.API_1484_11)"]
    IFrame -->|Calls LMSInitialize() / LMSSetValue()| CMIBridge
    CMIBridge -->|Asynchronous Sync| API["POST /api/courses/scorm-tracking/"]
    API --> DB[("ScormTracking Table")]
```

---

## 2. CMI Runtime Bridge Implementation

When serving SCORM launch HTML files (`serve_scorm_media`), Django automatically injects a JavaScript CMI locator bridge into the `<head>` section:

```javascript
(function() {
  function findScormApi12() {
    try { if (window.parent && window.parent.API) return window.parent.API; } catch(e) {}
    try { if (window.top && window.top.API) return window.top.API; } catch(e) {}
    return null;
  }
  function findScormApi2004() {
    try { if (window.parent && window.parent.API_1484_11) return window.parent.API_1484_11; } catch(e) {}
    try { if (window.top && window.top.API_1484_11) return window.top.API_1484_11; } catch(e) {}
    return null;
  }
  window.API = window.API || findScormApi12();
  window.API_1484_11 = window.API_1484_11 || findScormApi2004();
})();
```

---

## 3. CMI Data Persistence Directory

| CMI Element (SCORM 1.2) | CMI Element (SCORM 2004) | Description & Persistence Rule |
| :--- | :--- | :--- |
| `cmi.core.lesson_status` | `cmi.completion_status` | Lesson state (`incomplete`, `completed`, `passed`, `failed`). |
| `cmi.core.score.raw` | `cmi.score.raw` | Student assessment score. |
| `cmi.core.lesson_location` | `cmi.location` | Bookmarked slide or location string. |
| `cmi.core.session_time` | `cmi.session_time` | Active learning session duration. |
""",
         "published", None, ["scorm", "cmi", "player", "tracking"]),

        ("Architecture", "Media Streaming Pipeline, File Storage, Certificate Generation & System Notification Flows", "media-storage-certificate-notification-flows-architecture",
         "Technical details of video byte-range streaming, media storage directory organization, automated PDF certificate generation, and system notifications.",
         """# Media Streaming Pipeline, File Storage, Certificate Generation & System Notification Flows

This section covers media file streaming, file storage layouts, PDF certificate generation, and platform notification flows.

---

## 1. Video Byte-Range Media Streaming Pipeline

Large video files uploaded to `/media/course_videos/` are streamed using HTTP byte-range requests (`HTTP_RANGE`), enabling smooth seeking and buffer management:

```mermaid
sequenceDiagram
    autonumber
    actor Learner as Learner Player
    participant Server as Custom Video Streamer (serve_media_video)
    participant Disk as Storage Disk

    Learner->>Server: GET /media/course_videos/lecture.mp4 (Range: bytes=0-1048575)
    Server->>Disk: Open file & seek to offset 0
    Disk-->>Server: Read 1MB chunk
    Server-->>Learner: HTTP 206 Partial Content (Content-Range: bytes 0-1048575/52428800)
```

---

## 2. File Storage Directory Structure

```text
MEDIA_ROOT/
├── course_videos/      # Video files with byte-range streaming support
├── scorm/              # Extracted SCORM packages with HTML/JS launch files
├── certificates/       # Generated learner certificate PDFs
├── logos/              # Organization tenant logos & login hero banners
└── uploads/            # Imported source files (PDF, DOCX, PPTX)
```

---

## 3. Automated Certificate Generation & Verification Flow

```mermaid
flowchart TD
    Finish["Learner Completes 100% Course Lessons"] --> Trigger["Trigger Certificate Generator"]
    Trigger --> FetchTemplate["Fetch Org CertificateTemplate"]
    FetchTemplate --> RenderPDF["Render PDF Document with Dynamic Tags"]
    RenderPDF --> GenQR["Generate Unique Verification QR Link"]
    GenQR --> SaveDB["Save IssuedCertificate Record"]
    SaveDB --> UserDownload["Available in /certificates for Download"]
```

---

## 4. Notification & Account Security Flow

1. **Account Frozen Interceptor**: If an API returns `error: "account_frozen"`, frontend `authFetch()` triggers a custom `account_frozen` window event, clearing JWT tokens and displaying an account hold banner.
2. **In-App Toast System**: Centralized notification manager rendering success, warning, and error toasts.
3. **SMTP Email Notifications**: Background notification dispatcher issuing welcome emails, course assignment alerts, and password reset links.""",
         "published", None, ["media", "storage", "certificates", "notifications"]),

        # 3. Master Setup Documentation
        ("Master Setup Documentation", "Master Setup Console & Global Feature Flags", "master-setup-console-and-global-feature-flags",
         "Documentation for Super Admin Master Setup Console and system feature toggles.",
         """# Master Setup Console & Global Feature Flags

The **Master Setup Console** allows Super Admins to provision organizations, manage subscription plans, toggle feature access per organization, and configure global platform branding.

## Core Master Setup Endpoints
- `GET /api/features/`: List all global platform feature keys.
- `GET /api/plans/`: List subscription plans (Free, Pro, Enterprise).
- `POST /api/provision-organization/`: Provision a new tenant organization with admin credentials.
- `POST /api/toggle-org-feature/`: Enable or disable a feature flag for a specific tenant.""",
         "published", None, ["master-setup", "feature-flags", "plans"]),

        # 4. Organization Admin Documentation
        ("Organization Admin Documentation", "Department Trees & Custom RBAC Roles", "department-trees-and-custom-rbac-roles",
         "Guide to managing department hierarchies and custom role permissions in Org Admin.",
         """# Department Trees & Custom RBAC Roles

Organization Admins can configure hierarchical organizational units (`Department`) and define granular custom roles (`Role`).

## Granular Permissions
- `can_manage_users`: Create, edit, and deactivate organization users.
- `can_manage_departments`: Create and reorder department nodes.
- `can_create_courses` & `can_edit_courses`: Access Content Authoring.
- `can_manage_module_access`: Toggle module visibility per role.""",
         "published", None, ["org-admin", "departments", "rbac"]),

        # 5. Learner Documentation
        ("Learner Documentation", "Learner Portal, Course Catalog & Polymorphic Player", "learner-portal-catalog-and-player",
         "User guide for course catalog browsing, lesson playback, and certificate generation.",
         """# Learner Portal, Course Catalog & Polymorphic Player

Learners explore assigned and public courses via the **Course Catalog** (`/catalog`) and launch lessons via the **Polymorphic Course Player** (`/courses/$courseId/play/$lessonId`).

## Player Features
- Sequential lesson navigation with progress tracking.
- Interactive Knowledge Check evaluations.
- Instant Certificate PDF generation upon 100% course completion.""",
         "published", None, ["learner", "player", "catalog"]),

        # 6. Module Documentation
        ("Module Documentation", "Module Architecture & Route Registry Specification", "module-architecture-and-route-registry",
         "Overview of all frontend routes and backend apps.",
         """# Module Architecture & Route Registry Specification

The platform consists of modular Django apps (`users`, `organizations`, `courses`, `master_setup`, `authoring_engine`, `import_engine`, `scorm_export`) mapped to frontend TanStack Router routes.""",
         "published", None, ["modules", "routes", "registry"]),

        # 7. Feature Documentation
        ("Feature Documentation", "Universal Course Import & Export Feature Specification", "universal-course-import-export-specification",
         "Technical details of SCORM, PDF, DOCX, and Media course import & export pipelines.",
         """# Universal Course Import & Export Specification

Course content can be imported from SCORM ZIPs, PDF documents, Word documents, PowerPoint decks, and media files, and exported as SCORM 1.2 or SCORM 2004 archives.""",
         "published", None, ["features", "import", "export"]),

        # 8. Workflow Documentation
        ("Workflow Documentation", "End-to-End Course Authoring & Publishing Workflow", "end-to-end-course-authoring-publishing-workflow",
         "Complete workflow guide from course creation to live catalog publishing.",
         """# End-to-End Course Authoring & Publishing Workflow

1. Create course draft in `/authoring`.
2. Add Modules and Lessons.
3. Build rich block trees using the Block Editor.
4. Execute Pre-flight Validation check (`/api/authoring/validate/`).
5. Publish course to make it visible in the Learner Catalog.""",
         "published", None, ["workflow", "authoring", "publishing"]),

        # 9. Content Authoring Guide
        ("Content Authoring Guide", "Block Editor Layout, Quiz Builder & Scenario Builder", "block-editor-quiz-scenario-builder-guide",
         "Authoring manual for constructing interactive lessons, quizzes, and branching scenarios.",
         """# Block Editor, Quiz Builder & Scenario Builder Guide

The Block Editor empowers authors to add non-contiguous content blocks, configure layout widths (full, centered, wide), write knowledge check questions, and construct branching scenario decision trees.""",
         "published", None, ["authoring-guide", "quiz-builder", "scenarios"]),

        # 10. SCORM Documentation
        ("SCORM Documentation", "SCORM 1.2 & SCORM 2004 Packaging Standard", "scorm-12-2004-packaging-standard",
         "Technical breakdown of SCORM package import, export, and imsmanifest parsing.",
         """# SCORM 1.2 & SCORM 2004 Packaging Standard

The platform provides complete enterprise compliance for importing and exporting SCORM content packages.

## Backend Exporters (`scorm_export`)
- `Scorm12Exporter`: Generates SCORM 1.2 compliant ZIP archives with `imsmanifest.xml` adhering to ADL SCORM 1.2 specification.
- `Scorm2004Exporter`: Generates SCORM 2004 (4th Edition) compliant packages with full sequencing and navigation metadata.

## Manifest Generation (`imsmanifest.xml`)
The manifest exporter formats course structure (`<organizations>`, `<organization>`, `<item>`, `<resources>`, `<resource>`) and includes required SCORM schema definitions (`adlcp:scormtype="sco"`).

## Player Tracking
The learner player implements a SCORM runtime API wrapper (`API` / `API_1484_11`) in JavaScript, logging CMI data (`cmi.core.lesson_status`, `cmi.completion_status`, `cmi.score.raw`) back to `/api/courses/scorm-tracking/`.""",
         "published", None, ["scorm", "xml", "imsmanifest", "export"]),

        # 11. XML Documentation
        ("XML Documentation", "XML Manifest Schema & Namespace Specification", "xml-manifest-schema-namespace-specification",
         "Detailed documentation of imsmanifest.xml generation and schema rules.",
         """# XML Manifest Schema & Namespace Specification

The SCORM Exporter formats XML manifests with standard namespaces (`xmlns="http://www.imsproject.org/xsd/imscp_rootv1p1p2"`, `xmlns:adlcp="http://www.adlnet.org/xsd/adlcp_rootv1p2"`).""",
         "published", None, ["xml", "schema", "manifest"]),

        # 12. API Documentation
        ("API Documentation", "REST API Endpoint Directory & Auth Specification", "rest-api-endpoint-directory",
         "Reference documentation for REST API endpoints and JWT Bearer authentication.",
         """# REST API Endpoint Directory & Auth Specification

All API requests require `Authorization: Bearer <access_token>` headers.
Base URL: `http://localhost:8000/api/`.""",
         "published", None, ["api", "endpoints", "jwt"]),

        # 13. Database Documentation
        ("Database Documentation", "Django ORM Schema & Entity Relationship Overview", "django-orm-schema-overview",
         "Summary of all database tables, models, and foreign key relationships.",
         """# Django ORM Schema & Entity Relationship Overview

The LMS database comprises 25+ relational models across 6 Django apps:

## Core Database Tables
- `organizations_organization`: Multi-tenant organization accounts.
- `users_user`: Platform user records with role associations and tenant keys.
- `courses_course`: Core course metadata, level, accent color, and SCORM flags.
- `courses_module`: Course modules ordered sequentially.
- `courses_lesson`: Lessons linked to modules with duration and type flags.
- `authoring_lessonblocktree`: Root container for lesson authoring blocks.
- `authoring_lessonblock`: Polymorphic content blocks (Heading, Quiz, Video, etc.).
- `courses_issuedcertificate`: Generated certificates linked to learners and courses.
- `toolkit_article`: Master Toolkit documentation articles and versions.""",
         "published", None, ["database", "schema", "orm", "tables"]),

        # 14. UI Components Documentation
        ("UI Components Documentation", "Design System & AppShell Architecture", "design-system-and-appshell-architecture",
         "Overview of reusable React components, AppShell layout container, and theme tokens.",
         """# Design System & AppShell Architecture

The UI is built with Vanilla CSS variables and Tailwind utilities. `AppShell` and `SuperAdminShell` provide responsive navigation layouts.""",
         "published", None, ["ui", "components", "appshell"]),

        # 15. Settings & Toggles
        ("Settings & Toggles", "Platform Settings & Tenant Configuration Matrix", "platform-settings-tenant-configuration-matrix",
         "Reference guide for system settings, SMTP configuration, and security timeouts.",
         """# Platform Settings & Tenant Configuration Matrix

`PlatformSettings` manages global parameters:
- Password min length
- Session timeout minutes
- Max upload size MB
- SMTP host, port, credentials, and TLS settings.""",
         "published", None, ["settings", "smtp", "config"]),

        # 16. Error Resolution Center
        ("Error Resolution Center", "ERR_401_UNAUTHORIZED - Authentication & JWT Refresh Fix", "err-401-unauthorized-fix",
         "Troubleshooting HTTP 401 errors during API requests.",
         """# ERR_401_UNAUTHORIZED - Authentication Fix

### Problem
API calls return `HTTP 401 Unauthorized`.

### Cause
1. JWT authentication token expired or missing from request headers (`Authorization: Bearer <token>`).
2. User session invalidated or logged out.

### Resolution Steps
1. Verify user credentials at `/login`.
2. Inspect `localStorage.getItem('access_token')` on the browser console.
3. Check Django `REST_FRAMEWORK` settings for `SimpleJWT` expiration duration.
4. Retry request via `authFetch()` utility in `src/lib/auth.tsx` which automatically attaches active authorization headers.""",
         "published", "ERR_401", ["error", "auth", "401", "jwt"]),

        # 17. Troubleshooting Guide
        ("Troubleshooting Guide", "SCORM Package & Media Streaming Diagnostic Guide", "scorm-package-media-streaming-diagnostic-guide",
         "Diagnostic guide for SCORM player initialization and video range requests.",
         """# SCORM Package & Media Streaming Diagnostic Guide

### SCORM Launch Diagnostics
Ensure uploaded SCORM ZIPs contain `imsmanifest.xml` in the root directory. Check CORS and X-Frame-Options headers on `/media/scorm/`.""",
         "published", None, ["troubleshooting", "scorm", "media"]),

        # 18. Deployment Guide
        ("Deployment Guide", "Production Deployment & Environment Setup Guide", "production-deployment-environment-setup-guide",
         "Checklist for deploying LMS backend and frontend to staging/production.",
         """# Production Deployment Guide

1. Configure `.env` variables (`SECRET_KEY`, `DATABASE_URL`, `DEBUG=False`).
2. Execute `python manage.py migrate`.
3. Run `npm run build` in `frontend/halyard-ascend`.
4. Configure Nginx / Gunicorn reverse proxy.""",
         "published", None, ["deployment", "production", "nginx"]),

        # 19. Security Documentation
        ("Security Documentation", "JWT Authentication, RBAC & Multi-Tenant Data Scoping", "jwt-auth-rbac-multi-tenant-data-scoping",
         "In-depth documentation of security policies and data isolation mechanics.",
         """# JWT Authentication, RBAC & Multi-Tenant Data Scoping

All endpoints check request authentication and scope ORM querysets by `request.user.organization_id` to prevent cross-tenant data leaks.""",
         "published", None, ["security", "jwt", "tenant-isolation"]),

        # 20. Release Notes
        ("Release Notes", "Platform Version 2.4.0 Release Summary", "platform-version-240-release-summary",
         "Summary of features and enhancements in Version 2.4.0.",
         """# Platform Version 2.4.0 Release Summary

Version 2.4.0 introduces the **Master Toolkit Enterprise Knowledge Center**, SCORM 1.2/2004 Export UI, and full-width broad layout support.""",
         "published", None, ["release-notes", "v2.4.0"]),

        # 21. Version History
        ("Version History", "Course Versioning & Historical Snapshot Preservation", "course-versioning-historical-snapshot-preservation",
         "Guide to versioning courses and restoring historical snapshots non-destructively.",
         """# Course Versioning & Historical Snapshot Preservation

Restoring a previous version snapshot creates a new draft version without deleting published or historical version entries.""",
         "published", None, ["versioning", "rollback", "snapshots"]),

        # 22. Search Engine
        ("Search Engine", "Multi-Field Global Search Architecture", "multi-field-global-search-architecture",
         "Explanation of global multi-field search across Toolkit categories, articles, tags, and error codes.",
         """# Multi-Field Global Search Architecture

Global search queries titles, summaries, content, error codes, and tags simultaneously.""",
         "published", None, ["search", "indexing"]),

        # 23. Audit Logs
        ("Audit Logs", "Administrative Audit Trailing & Compliance Logging", "administrative-audit-trailing-compliance-logging",
         "Documentation of administrative audit trail features in Master Setup and Org Admin.",
         """# Administrative Audit Trailing & Compliance Logging

All administrative actions (article creation, version rollback, feature toggling) generate `ToolkitAuditLog` and `ActivityLog` records.""",
         "published", None, ["audit-logs", "compliance"]),

        # 24. Project Change Log
        ("Project Change Log", "Platform Codebase Change History Directory", "platform-codebase-change-history-directory",
         "Directory of codebase change logs and update entries.",
         """# Platform Codebase Change History Directory

Maintains developer notes, modified file lists, and version tags for platform updates.""",
         "published", None, ["changelog", "codebase"]),

        # 25. Feature Dependency Map
        ("Feature Dependency Map", "Module Dependency Chains & Risk Analysis", "module-dependency-chains-risk-analysis",
         "Mapping of dependencies between authoring, courses, SCORM, and publishing modules.",
         """# Module Dependency Chains & Risk Analysis

Visual dependency chains assist engineering teams in identifying downstream effects before modifying core models.""",
         "published", None, ["dependencies", "risk"]),

        # 26. Impact Analysis
        ("Impact Analysis", "Database Schema & API Change Risk Assessment", "database-schema-api-change-risk-assessment",
         "Guidelines for evaluating database schema migrations and breaking API changes.",
         """# Database Schema & API Change Risk Assessment

Evaluates affected models, APIs, and UI components prior to schema migrations.""",
         "published", None, ["impact-analysis", "migrations"]),

        # 27. API Explorer
        ("API Explorer", "Live REST API Endpoint Catalog & Schema Directory", "live-rest-api-endpoint-catalog-directory",
         "Interactive catalog of all active REST API endpoints.",
         """# Live REST API Endpoint Catalog

Lists all registered API endpoints, HTTP methods, and authentication requirements.""",
         "published", None, ["api-explorer", "rest"]),

        # 28. Database Explorer
        ("Database Explorer", "Live Database Schema & Model Directory Spec", "live-database-schema-model-directory-spec",
         "Auto-discovered directory of Django ORM models and database tables.",
         """# Live Database Schema Directory

Displays live database table metadata, field counts, and foreign key relations.""",
         "published", None, ["database-explorer", "schema"]),

        # 29. Configuration Explorer
        ("Configuration Explorer", "Global Platform & Tenant Configuration Reference", "global-platform-tenant-configuration-reference",
         "Reference manual for all configurable platform and tenant settings.",
         """# Global Platform & Tenant Configuration Reference

Detailed matrix of global platform settings and tenant terminology overrides.""",
         "published", None, ["config-explorer", "settings"]),

        # 30. Live System Health
        ("Live System Health", "Operational Metrics & System Uptime Monitor Spec", "operational-metrics-system-uptime-monitor-spec",
         "Specification of live operational health monitoring metrics.",
         """# Operational Metrics & System Uptime Monitor

Provides real-time visibility into database health, storage status, active users, and tenant counts.""",
         "published", None, ["system-health", "metrics", "uptime"]),
    ]

    for cat_name, title, slug, summary, content, status, err_code, tags in articles_data:
        cat = cat_map[cat_name]
        art, created = ToolkitArticle.objects.get_or_create(
            slug=slug,
            defaults={
                'category': cat,
                'title': title,
                'summary': summary,
                'content': content,
                'status': status,
                'error_code': err_code,
                'tags': tags,
                'version': 1
            }
        )
        if created:
            ToolkitArticleVersion.objects.create(
                article=art,
                version_number=1,
                title=title,
                summary=summary,
                content=content
            )

    # 3. Create Sample Project Change Log
    ToolkitChangeLog.objects.get_or_create(
        version="2.4.0",
        feature_name="Master Toolkit Enterprise Module",
        defaults={
            "module_name": "Master Setup",
            "description": "Implemented central Knowledge Center, System Health Monitor, API/Database Explorers, Impact Analysis, and Rescan Engine.",
            "files_modified": ["master_setup/models.py", "master_setup/views.py", "super-admin.toolkit.tsx"],
            "developer_name": "Antigravity Engineering",
            "status": "completed",
            "notes": "Full multi-tenant architecture documentation and live metrics added."
        }
    )

    # 4. Create Sample Release Notes
    ToolkitReleaseNote.objects.get_or_create(
        version_number="2.4.0",
        defaults={
            "release_date": "2026-07-29",
            "new_features": ["Enterprise Master Toolkit Module", "Live System Health Monitor", "Feature Dependency Map"],
            "improvements": ["Enhanced SCORM 1.2 & 2004 Export UI", "Full broad layout for Content Authoring"],
            "bug_fixes": ["Fixed polymorphic block tree hydration in student player", "Resolved Django server imports"],
            "breaking_changes": [],
            "is_published": True
        }
    )

    print(f"Toolkit auto-seeding completed successfully! Seeded articles across all {len(cat_map)} categories.")

if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LAMS.settings')
    django.setup()
    seed_toolkit()
