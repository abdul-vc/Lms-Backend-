import sqlite3

conn = sqlite3.connect('db.sqlite3')
c = conn.cursor()

c.execute('SELECT id,name,status,sub_domain FROM organizations_organization ORDER BY id')
rows = c.fetchall()
result_lines = []
result_lines.append(f'TOTAL_ORGS: {len(rows)}')
active = sum(1 for r in rows if r[2].lower() == 'active')
result_lines.append(f'ACTIVE_ORGS: {active}')
for r in rows:
    result_lines.append(f'ORG id={r[0]} name={r[1]!r} status={r[2]!r} sub={r[3]!r}')

c.execute('SELECT id,username,email,is_platform_super_admin,organization_id FROM users_user ORDER BY id')
users = c.fetchall()
result_lines.append(f'TOTAL_USERS: {len(users)}')
for u in users:
    result_lines.append(f'USER id={u[0]} username={u[1]!r} email={u[2]!r} superadmin={u[3]} org_id={u[4]}')

conn.close()

with open('audit_out.txt', 'w') as f:
    f.write('\n'.join(result_lines))

print('Done. See audit_out.txt')
