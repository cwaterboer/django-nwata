"""
Management command to migrate existing users to UserOrgRole with owner role
"""
from django.core.management.base import BaseCommand
from api.models import User, Organization, UserOrgRole, Role, OrganizationState


class Command(BaseCommand):
    help = 'Migrate existing users to UserOrgRole schema with owner role'

    def handle(self, *args, **options):
        self.stdout.write('Migrating existing users to RBAC schema...')
        
        # Get owner role
        try:
            owner_role = Role.objects.get(name='owner')
        except Role.DoesNotExist:
            self.stdout.write(self.style.ERROR('Owner role not found. Run init_roles first.'))
            return
        
        # Get all users
        users = User.objects.select_related('org').all()
        
        migrated_count = 0
        skipped_count = 0
        org_state_count = 0
        
        for user in users:
            # Check if user already has a role
            existing_role = UserOrgRole.objects.filter(
                user=user,
                organization=user.org
            ).first()
            
            if existing_role:
                self.stdout.write(f'  Skipped {user.email} - already has role')
                skipped_count += 1
                continue
            
            # Create UserOrgRole with owner role and active state
            UserOrgRole.objects.create(
                user=user,
                organization=user.org,
                role=owner_role,
                state='active',
                invited_by=None,  # Original users, no inviter
                invited_at=user.created_at,
                accepted_at=user.created_at,
            )
            
            self.stdout.write(self.style.SUCCESS(f'  Migrated {user.email} as owner of {user.org.name}'))
            migrated_count += 1
        
        # Create organization states for all orgs
        organizations = Organization.objects.all()
        
        for org in organizations:
            org_state, created = OrganizationState.objects.get_or_create(
                organization=org,
                defaults={
                    'current_state': 'active',  # Existing orgs are active
                    'state_changed_at': org.created_at,
                }
            )
            
            if created:
                self.stdout.write(self.style.SUCCESS(f'  Created state for {org.name}'))
                org_state_count += 1
        
        self.stdout.write(self.style.SUCCESS(f'\nMigration complete!'))
        self.stdout.write(f'Users migrated: {migrated_count}')
        self.stdout.write(f'Users skipped: {skipped_count}')
        self.stdout.write(f'Organization states created: {org_state_count}')
