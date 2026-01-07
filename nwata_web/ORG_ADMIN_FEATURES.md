# Organization Administration System

This document describes the organization administration features for managing team members, roles, and permissions.

## Overview

The organization administration system provides comprehensive team management capabilities built on top of the RBAC (Role-Based Access Control) system.

### Key Features

- **User Management**: Invite, manage, and remove team members
- **Role-Based Access**: Assign roles (member, admin) to team members
- **Audit Logging**: Track all changes made to the organization
- **Permission Enforcement**: Fine-grained access control based on permissions
- **Department Management**: Organize members into departments (team orgs only)

## Architecture

### Role Hierarchy

1. **Owner** - Full control, cannot be changed by others
2. **Admin** - Manage users and org settings, except billing
3. **Member** - Standard team member with limited view access
4. **Viewer** - Read-only access to activity logs

### Permissions System

14 distinct permissions control what users can do:

| Permission | Owner | Admin | Member | Viewer |
|-----------|-------|-------|--------|--------|
| invite_users | ✓ | ✓ | | |
| remove_users | ✓ | ✓ | | |
| manage_roles | ✓ | | | |
| view_own_activity | ✓ | ✓ | ✓ | ✓ |
| view_team_activity | ✓ | ✓ | ✓ | |
| export_own_data | ✓ | ✓ | ✓ | |
| export_team_data | ✓ | ✓ | | |
| manage_org_settings | ✓ | ✓ | | |
| manage_billing | ✓ | | | |
| manage_modules | ✓ | ✓ | | |
| create_departments | ✓ | ✓ | | |
| manage_departments | ✓ | ✓ | | |
| view_audit_logs | ✓ | ✓ | | |
| manage_api_keys | ✓ | ✓ | | |

## User Management

### Inviting Users

**Endpoint**: `GET/POST /dashboard/org/users/`

Administrators can invite new users by:

1. Entering their email address
2. Selecting their initial role
3. Submitting the invitation

The system will:
- Create a `UserOrgRole` with state `invited`
- Generate an invitation token
- Send an invitation email (TODO: implement email sending)
- Log the action to audit log

### User States

Users can be in the following states:

- **pending** - Email provided but user hasn't signed up yet
- **invited** - User exists and invitation sent
- **active** - User has accepted invitation
- **rejected** - User declined invitation
- **expired** - Invitation not accepted within 7 days

### Managing Roles

**Endpoint**: `GET/POST /dashboard/org/users/<user_id>/role/`

Change a user's role:

```python
# From the change_user_role view
# Validates:
# - User is owner/admin
# - Target user is not owner
# - Not changing own role
# - New role is valid
# Logs change to AuditLog
```

### Removing Users

**Endpoint**: `GET/POST /dashboard/org/users/<user_id>/remove/`

Remove a user from organization:

```python
# Requires confirmation
# Validates:
# - Target is not owner
# - Not removing self
# Creates audit log entry
# Permanently deletes UserOrgRole
```

## Audit Logging

### Audit Log Model

Every change is logged with:
- **actor** - User who made the change (null for system actions)
- **action** - created, updated, deleted, state_changed
- **resource_type** - user, role, permission, org, dept
- **object_id** - ID of affected object
- **changes_before** - JSON of previous state
- **changes_after** - JSON of new state
- **timestamp** - When change occurred
- **ip_address** - Source IP address

### Viewing Logs

**Endpoint**: `GET /dashboard/org/audit-log/`

Requires `view_audit_logs` permission.

```html
<!-- Shows table of recent audit entries -->
<!-- Click "View" to see detailed before/after JSON -->
```

## Department Management

### Departments (Team Orgs Only)

**Endpoint**: `GET /dashboard/org/departments/`

Features:

- Hierarchical structure (departments can have parent departments)
- Department membership tracking
- Department-level role assignments

### Structure

```
Organization
├── Department (Finance)
│   ├── UserDepartment (Alice - Finance Lead)
│   └── UserDepartment (Bob - Finance Member)
├── Department (Engineering)
│   ├── Department (Frontend)
│   │   └── UserDepartment (Charlie - Frontend Dev)
│   └── Department (Backend)
│       └── UserDepartment (Diana - Backend Lead)
```

## Security Considerations

### Permission Enforcement

All views use decorators to enforce permissions:

```python
from api.permissions import require_org_admin, require_org_member

@login_required
@require_org_admin  # Requires owner or admin role
def manage_users(request):
    # request.organization - injected by middleware
    # request.user_permissions - set of permission codenames
    pass

@login_required
@require_org_member()  # Requires active membership
def view_audit_log(request):
    pass
```

### Middleware Integration

`OrganizationContextMiddleware` injects on every request:

```python
request.organization  # Current org (if user is member)
request.user_role    # UserOrgRole instance
request.user_permissions  # Set of permission codenames
request.can_manage_org  # Boolean (owner or admin)
```

### State Machine Transitions

User invitations follow state transitions:

```
pending → invited → active
              ↓
          expired (7 days)
              ↓
          rejected (user declines)
```

## API Integration

Forms are provided for:

- `InviteUserForm` - Email + Role selection
- `ChangeUserRoleForm` - Role selection for existing user
- `RemoveUserForm` - Confirmation checkbox

All forms validate input and check permissions.

## URL Routes

```python
# In dashboard/urls.py
path('org/users/', manage_users, name='manage_users')
path('org/users/<int:user_id>/role/', change_user_role, name='change_user_role')
path('org/users/<int:user_id>/remove/', remove_user, name='remove_user')
path('org/audit-log/', view_audit_log, name='view_audit_log')
path('org/departments/', manage_departments, name='manage_departments')
```

## Templates

### manage_users.html
- Shows active members in table
- Shows pending invitations
- Invite form at top
- Action links (change role, remove)

### change_user_role.html
- User email (read-only)
- Current role (read-only)
- New role selector
- Submit/Cancel buttons

### remove_user.html
- Confirmation checkbox
- Explains what will happen
- Submit/Cancel buttons

### audit_log.html
- Table of recent changes
- Timestamp, user, action, resource, details
- Expandable details for each entry

### manage_departments.html
- Shows all departments
- Parent-child relationships
- Member counts
- Edit/Delete actions (TODO)

## Implementation Checklist

- [x] User invitation form and view
- [x] Role change functionality
- [x] User removal with confirmation
- [x] Audit log display
- [x] Department structure
- [ ] Email invitation sending
- [ ] Accept invitation view
- [ ] Department creation UI
- [ ] API key management
- [ ] Payment state machine integration

## Next Steps

1. **Email System**: Implement `send_invitation_email()` function
2. **Accept Invitations**: Create `AcceptInvitationView` at `/invite/<token>/`
3. **Dashboard Integration**: Add team management links to navigation
4. **Department CRUD**: Complete department creation/editing
5. **API Keys**: Implement scoped API key management
6. **Payment Hooks**: Integrate with payment provider for state transitions

## Database Models

See [RBAC Documentation](../api/RBAC.md) for full schema details.

Key models:
- `Organization` - Company/team
- `User` - Nwata user
- `UserOrgRole` - User membership in org with role
- `Role` - Permission level (owner, admin, member, viewer)
- `Permission` - Specific action permission
- `RolePermission` - Maps roles to permissions
- `Department` - Hierarchical team grouping
- `UserDepartment` - User membership in department
- `AuditLog` - Change history
- `OrganizationState` - Lifecycle tracking

