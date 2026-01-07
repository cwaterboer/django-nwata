# Quick Reference: Organization Admin Features

## URLs

```
/dashboard/org/users/                 - Manage team members
/dashboard/org/users/<id>/role/      - Change user role
/dashboard/org/users/<id>/remove/    - Remove user
/dashboard/org/audit-log/            - View changes
/dashboard/org/departments/          - Manage departments
```

## Permission Decorators

```python
from api.permissions import (
    require_org_admin,
    require_org_member,
    require_permission,
    require_role
)

# Usage
@require_org_admin
def admin_view(request):
    pass

@require_org_member()
def member_view(request):
    pass

@require_permission('view_audit_logs')
def audit_view(request):
    pass

@require_role('owner')
def owner_view(request):
    pass
```

## Request Context (from Middleware)

```python
def my_view(request):
    org = request.organization          # Organization instance
    role = request.user_role            # UserOrgRole instance
    perms = request.user_permissions    # Set of permission codenames
    is_admin = request.can_manage_org   # Boolean
```

## Models

```python
from api.models import (
    Organization,          # Company/team
    User,                  # Nwata user
    UserOrgRole,          # User membership + role
    Role,                 # owner, admin, member, viewer
    Permission,           # Specific action
    Department,           # Hierarchical team
    UserDepartment,       # Dept membership
    AuditLog,             # Change history
    OrganizationState,    # Org lifecycle
    APIKey,               # Scoped API access
)
```

## Permission Names (14 total)

```
invite_users           - Invite new users
remove_users           - Remove users
manage_roles           - Change user roles
view_own_activity      - See own activity
view_team_activity     - See team activity
export_own_data        - Export own data
export_team_data       - Export team data
manage_org_settings    - Change org settings
manage_billing         - Manage billing (owner only)
manage_modules         - Enable/disable modules
create_departments     - Create departments
manage_departments     - Edit/delete departments
view_audit_logs        - View change history
manage_api_keys        - Create/revoke API keys
```

## Roles

| Role | Use Case | Perms |
|------|----------|-------|
| owner | Creator/full control | 14/14 |
| admin | Management (no billing) | 12/14 |
| member | Regular team member | 3/14 |
| viewer | Read-only access | 1/14 |

## Forms

```python
from dashboard.org_admin_forms import (
    InviteUserForm,      # Email + role
    ChangeUserRoleForm,  # New role
    RemoveUserForm,      # Confirmation
)
```

## Common Patterns

### Check Permission in View

```python
if 'manage_org_settings' not in request.user_permissions:
    return HttpResponseForbidden()
```

### Get User's Org

```python
try:
    nwata_user = User.objects.get(email=request.user.email)
    org = nwata_user.org
except User.DoesNotExist:
    org = None
```

### Check User Role

```python
from api.permissions import is_org_admin
if is_org_admin(request.user, org):
    # Show admin options
```

### Log Custom Action

```python
from api.models import AuditLog
AuditLog.objects.create(
    actor=request.user.nwata_user,
    action='created',
    resource_type='custom_resource',
    object_id='123',
    changes_after={'field': 'value'},
    ip_address=_get_client_ip(request)
)
```

## Management Commands

```bash
# Initialize roles and permissions
python manage.py init_roles

# Migrate existing users to RBAC
python manage.py migrate_users_to_rbac
```

## State Machines

### Organization States

```
created ─→ active ─→ suspended ─→ archived
           ↑                ↓
           └────────────────┘
```

### User Invitation States

```
pending ─→ invited ─→ active
              ├─→ expired (7 days)
              ├─→ rejected
              └─→ removed
```

## Common Errors & Solutions

**"You don't have access to any organization"**
- User not in UserOrgRole with active state
- Check: `UserOrgRole.objects.filter(user=user, state='active')`

**"Permission denied"**
- Check required permission in request.user_permissions
- Use decorator: `@require_permission('action_name')`

**"Cannot change owner's role"**
- Only owners can change themselves or other admins
- Check: `role.name == 'owner'`

**"User already in organization"**
- Check: `UserOrgRole.objects.filter(user=user, organization=org)`
- Can't invite same user twice

## Testing Checklist

- [ ] User can invite another user
- [ ] Invited user appears in pending list
- [ ] Admin can change member role
- [ ] Admin can remove member
- [ ] Owner cannot be removed
- [ ] Cannot remove yourself
- [ ] Audit log shows all changes
- [ ] Permissions enforced on views
- [ ] Non-admins can't access /org/users/

## Next Steps

1. **Implement Email Sending**
   - Uncomment TODO in manage_users view
   - Call `send_invitation_email(email, org, inviter, token_url)`

2. **Create Accept Invitation View**
   - Route: `/invite/<token>/`
   - Verify token, accept invitation
   - Transition: invited → active

3. **Add Dashboard Navigation**
   - Add link in sidebar (visible to admins only)
   - Show only for team orgs with admin+ role

4. **Permission Enforcement**
   - Wrap existing views with decorators
   - Test permission denials

5. **Complete Departments**
   - Add create/edit/delete views
   - Wire up user assignment

## Debug Tips

### View User's Permissions

```python
from api.permissions import get_user_permissions_in_org
perms = get_user_permissions_in_org(user, org)
print(perms)  # ['invite_users', 'remove_users', ...]
```

### Check Organization State

```python
org_state = org.organizationstate
print(org_state.current_state)  # 'active', 'suspended', etc.
```

### View Audit Log for User

```python
from api.models import AuditLog
logs = AuditLog.objects.filter(actor=user).order_by('-timestamp')
```

### View Recent Invitations

```python
from api.models import UserOrgRole
invites = UserOrgRole.objects.filter(
    organization=org,
    state__in=['pending', 'invited']
).order_by('-invited_at')
```

## Performance Considerations

- UserOrgRole has index on (organization, state)
- AuditLog has index on (timestamp) and (actor, timestamp)
- Use select_related('role', 'user') on queries
- Use prefetch_related for department members

## File Locations

```
api/
  models.py                     # RBAC models
  permissions.py                # Decorators & helpers
  middleware.py                 # Context injection
  signals.py                    # Audit logging
  state_machine.py              # State machines
  management/commands/
    init_roles.py               # Initialize roles
    migrate_users_to_rbac.py    # Migrate users

dashboard/
  org_admin_forms.py            # Forms
  org_admin_views.py            # Views
  templates/dashboard/
    manage_users.html
    change_user_role.html
    remove_user.html
    audit_log.html
    manage_departments.html

nwata_web/
  settings.py                   # Middleware config
  
templates/base_dashboard.html   # Base template
```

## Support for Future Features

All infrastructure is in place for:
- Multi-organization users (middleware prepared)
- Custom roles (Role model is extensible)
- Department-level permissions (UserDepartment structure ready)
- Scoped API access (APIKey model)
- Payment state transitions (OrganizationState machine)

