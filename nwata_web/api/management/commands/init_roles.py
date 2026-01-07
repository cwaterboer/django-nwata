"""
Management command to initialize default roles and permissions
"""
from django.core.management.base import BaseCommand
from api.models import Role, Permission, RolePermission


class Command(BaseCommand):
    help = 'Initialize default roles and permissions for RBAC system'

    def handle(self, *args, **options):
        self.stdout.write('Initializing roles and permissions...')
        
        # Create roles
        roles_data = [
            ('owner', 'Organization owner with full control'),
            ('admin', 'Administrator with management permissions'),
            ('member', 'Regular member with standard access'),
            ('viewer', 'Read-only access'),
        ]
        
        roles = {}
        for role_name, description in roles_data:
            role, created = Role.objects.get_or_create(
                name=role_name,
                defaults={'description': description}
            )
            roles[role_name] = role
            if created:
                self.stdout.write(self.style.SUCCESS(f'  Created role: {role_name}'))
            else:
                self.stdout.write(f'  Role exists: {role_name}')
        
        # Create permissions
        permissions_data = [
            # User Management
            ('invite_users', 'Invite new users to organization'),
            ('remove_users', 'Remove users from organization'),
            ('manage_roles', 'Change user roles'),
            
            # Data Access
            ('view_own_activity', 'View own activity data'),
            ('view_team_activity', 'View team activity data'),
            ('export_own_data', 'Export own data'),
            ('export_team_data', 'Export team data'),
            
            # Organization Management
            ('manage_org_settings', 'Manage organization settings'),
            ('manage_billing', 'Manage billing and subscriptions'),
            ('manage_modules', 'Enable/disable feature modules'),
            
            # Department Management
            ('create_departments', 'Create new departments'),
            ('manage_departments', 'Manage department structure'),
            
            # Advanced
            ('view_audit_logs', 'View audit logs'),
            ('manage_api_keys', 'Create and manage API keys'),
        ]
        
        permissions = {}
        for perm_name, description in permissions_data:
            perm, created = Permission.objects.get_or_create(
                name=perm_name,
                defaults={'description': description}
            )
            permissions[perm_name] = perm
            if created:
                self.stdout.write(self.style.SUCCESS(f'  Created permission: {perm_name}'))
            else:
                self.stdout.write(f'  Permission exists: {perm_name}')
        
        # Map permissions to roles
        role_permissions_map = {
            'owner': [
                # All permissions
                'invite_users', 'remove_users', 'manage_roles',
                'view_own_activity', 'view_team_activity',
                'export_own_data', 'export_team_data',
                'manage_org_settings', 'manage_billing', 'manage_modules',
                'create_departments', 'manage_departments',
                'view_audit_logs', 'manage_api_keys',
            ],
            'admin': [
                'invite_users', 'remove_users', 'manage_roles',
                'view_own_activity', 'view_team_activity',
                'export_own_data', 'export_team_data',
                'manage_org_settings', 'manage_modules',
                'create_departments', 'manage_departments',
                'view_audit_logs', 'manage_api_keys',
            ],
            'member': [
                'view_own_activity', 'view_team_activity',
                'export_own_data',
            ],
            'viewer': [
                'view_own_activity',
            ],
        }
        
        # Create role-permission mappings
        for role_name, perm_names in role_permissions_map.items():
            role = roles[role_name]
            for perm_name in perm_names:
                perm = permissions[perm_name]
                _, created = RolePermission.objects.get_or_create(
                    role=role,
                    permission=perm
                )
                if created:
                    self.stdout.write(f'  Assigned {perm_name} to {role_name}')
        
        self.stdout.write(self.style.SUCCESS('\nSuccessfully initialized roles and permissions!'))
        self.stdout.write(f'\nRoles created: {len(roles)}')
        self.stdout.write(f'Permissions created: {len(permissions)}')
