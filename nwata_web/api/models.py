from django.db import models
from django.contrib.auth.models import User as AuthUser
from django.utils import timezone
import hashlib
import secrets
import jsonschema
from jsonschema import validate, ValidationError

# ========================================
# CONTEXT DATA VALIDATION FUNCTIONS
# ========================================

CONTEXT_SCHEMA_V1 = {
    "type": "object",
    "properties": {
        "typing_count": {"type": "integer", "minimum": 0, "maximum": 10000},
        "scroll_count": {"type": "integer", "minimum": 0, "maximum": 5000},
        "shortcut_count": {"type": "integer", "minimum": 0, "maximum": 1000},
        "total_idle_ms": {"type": "integer", "minimum": 0},
        "max_idle_ms": {"type": "integer", "minimum": 0},
        "window_duration_s": {"type": "number", "minimum": 0.001, "maximum": 28800},
        "typing_rate_per_min": {"type": "number", "minimum": 0, "maximum": 1000},
        "scroll_rate_per_min": {"type": "number", "minimum": 0, "maximum": 500}
    },
    "required": ["typing_count", "scroll_count", "shortcut_count", "total_idle_ms", "max_idle_ms", "window_duration_s"]
}

def validate_context_schema(value):
    """Validate context data against schema"""
    if value is None:
        return
    validate(instance=value, schema=CONTEXT_SCHEMA_V1)

def validate_context_data(context_data):
    """Enhanced context validation with business rules"""
    if not context_data:
        return True, None, None
    
    try:
        validate_context_schema(context_data)
    except ValidationError as e:
        return False, [f"Schema validation failed: {e.message}"], None
    
    errors, warnings = [], []
    
    # Business rule checks
    duration = context_data.get('window_duration_s', 0)
    if duration <= 0:
        errors.append("window_duration_s must be positive")
    
    typing_rate = context_data.get('typing_rate_per_min', 0)
    if typing_rate > 1000:
        errors.append("typing_rate_per_min exceeds realistic bounds")
    elif typing_rate > 200:
        warnings.append("typing_rate_per_min unusually high")
    
    idle_ratio = context_data.get('total_idle_ms', 0) / max(duration * 1000, 1)
    if idle_ratio > 0.95:
        warnings.append("idle_ratio > 95% - mostly inactive window")
    
    return len(errors) == 0, errors, warnings

def compute_data_quality_score(context, start_time, end_time):
    """Compute data quality score for activity log (0-1 scale)"""
    score = 1.0
    
    # Context completeness
    if not context:
        score *= 0.7
    
    # Duration validity
    duration = (end_time - start_time).total_seconds()
    if duration <= 0 or duration > 28800:  # 8 hours max, positive duration
        score *= 0.5
    
    # Context consistency
    if context:
        if context.get('window_duration_s', 0) != duration:
            score *= 0.9  # Minor penalty for duration mismatch
        
        # Outlier detection
        typing_rate = context.get('typing_rate_per_min', 0)
        if typing_rate > 1000:  # Impossible typing speed
            score *= 0.8
    
    return score

def normalize_context_for_ml(context_data):
    """Transform context into ML-ready normalized features"""
    if not context_data:
        return {
            'has_context': False,
            'typing_count_norm': 0,
            'scroll_count_norm': 0,
            'idle_ratio': 0,
            'activity_intensity': 0
        }
    
    duration_s = context_data['window_duration_s']
    
    return {
        'has_context': True,
        'typing_count_norm': min(context_data['typing_count'] / max(duration_s, 1), 10),
        'scroll_count_norm': min(context_data['scroll_count'] / max(duration_s / 60, 1), 100),
        'idle_ratio': min(context_data['total_idle_ms'] / max(duration_s * 1000, 1), 1.0),
        'activity_intensity': (context_data['typing_count'] + context_data['scroll_count']) / max(duration_s, 1),
        'peak_idle_ratio': min(context_data['max_idle_ms'] / max(duration_s * 1000, 1), 1.0)
    }

class Organization(models.Model):
    ORG_TYPE_CHOICES = [
        ('personal', 'Personal'),
        ('team', 'Team'),
    ]
    
    name = models.CharField(max_length=255)
    subdomain = models.CharField(max_length=100, unique=True)
    organization_type = models.CharField(max_length=20, choices=ORG_TYPE_CHOICES, default='personal')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['subdomain']),
            models.Index(fields=['organization_type']),
        ]

    def __str__(self):
        return self.name
    
    def is_personal(self):
        return self.organization_type == 'personal'
    
    def is_team(self):
        return self.organization_type == 'team'
    
    @staticmethod
    def generate_personal_subdomain(email):
        """Generate stable, non-predictable subdomain for personal org from email"""
        hash_digest = hashlib.sha256(email.lower().encode()).hexdigest()[:12]
        return f"personal-{hash_digest}"

# legacy user record linking an auth user to an org; will be deprecated once
# we migrate to the new Membership model.  For now we keep it to ease transition.
class User(models.Model):
    email = models.EmailField(unique=True)
    org = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='users')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['org', 'created_at']),
        ]

    def __str__(self):
        return f"{self.email} ({self.org.name})"


# --- new multi‑membership architecture ---

class Membership(models.Model):
    ROLE_CHOICES = [
        ('owner', 'Owner'),
        ('admin', 'Admin'),
        ('member', 'Member'),
    ]
    LICENSE_CHOICES = [
        ('individual', 'Individual'),
        ('team', 'Team'),
    ]
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('pending', 'Pending'),
        ('invited', 'Invited'),
    ]

    auth_user = models.ForeignKey(
        'auth.User',
        on_delete=models.CASCADE,
        related_name='memberships'
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='memberships'
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='member')
    license_type = models.CharField(max_length=20, choices=LICENSE_CHOICES, default='individual')
    email_used = models.EmailField(help_text='Email address used to join this org')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [['auth_user', 'organization']]
        indexes = [
            models.Index(fields=['auth_user']),
            models.Index(fields=['organization']),
        ]

    def __str__(self):
        return f"{self.auth_user.email} @ {self.organization.name} ({self.role})"


class Device(models.Model):
    membership = models.ForeignKey(
        Membership,
        on_delete=models.CASCADE,
        related_name='devices',
        null=True,
        blank=True
    )
    device_name = models.CharField(max_length=255, default='Device')
    device_type = models.CharField(max_length=50, blank=True, default='')
    token = models.CharField(max_length=512, unique=True, null=True, blank=True)
    token_expires_at = models.DateTimeField(null=True, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['token']),
            models.Index(fields=['membership', 'token']),
        ]

    def __str__(self):
        return f"{self.device_name} ({self.membership})"


class Invite(models.Model):
    STATUS_CHOICES = [
        ('sent', 'Sent'),
        ('accepted', 'Accepted'),
        ('revoked', 'Revoked'),
    ]

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='invites'
    )
    email = models.EmailField(null=True, blank=True)
    role = models.CharField(max_length=20, choices=Membership.ROLE_CHOICES, default='member')
    license_type = models.CharField(max_length=20, choices=Membership.LICENSE_CHOICES, default='team')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='sent')
    token = models.CharField(max_length=255, unique=True, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Invite {self.email} to {self.organization.name} ({self.status})"

class ActivityLog(models.Model):
    # new schema: link log to membership and optionally device
    membership = models.ForeignKey('Membership', on_delete=models.CASCADE, related_name='activity_logs', null=True, blank=True)
    device = models.ForeignKey('Device', on_delete=models.SET_NULL, null=True, blank=True, related_name='activity_logs')
    # legacy field kept temporarily to ease migration
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='activity_logs', null=True, blank=True)
    app_name = models.CharField(max_length=255, db_index=True)
    window_title = models.CharField(max_length=500, null=True, blank=True)
    start_time = models.DateTimeField(db_index=True)
    end_time = models.DateTimeField()
    category = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    context = models.JSONField(null=True, blank=True, validators=[validate_context_schema])  # Context signals from agent
    context_schema_version = models.CharField(max_length=10, default='1.0')
    data_quality_score = models.FloatField(null=True, blank=True)  # 0-1 scale
    validation_errors = models.JSONField(null=True, blank=True)
    normalized_context = models.JSONField(null=True, blank=True)  # ML-ready features
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['app_name', 'created_at']),
            models.Index(fields=['start_time', 'end_time']),
            models.Index(fields=['data_quality_score']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        user_email = self.user.email if self.user else (self.membership.auth_user.email if self.membership else "Unknown")
        return f"{self.app_name} - {user_email} ({self.start_time})"

    @property
    def duration(self):
        """Calculate duration in seconds"""
        return (self.end_time - self.start_time).total_seconds()

    def save(self, *args, **kwargs):
        # Compute quality metrics before saving
        if self.context:
            self.data_quality_score = compute_data_quality_score(
                self.context, self.start_time, self.end_time
            )
            self.normalized_context = normalize_context_for_ml(self.context)
        
        super().save(*args, **kwargs)

class Gamification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='gamification_records')
    points = models.IntegerField(default=0)
    streak = models.IntegerField(default=0)
    date = models.DateField(db_index=True)

    class Meta:
        unique_together = [['user', 'date']]
        indexes = [
            models.Index(fields=['user', 'date']),
        ]
        ordering = ['-date']

    def __str__(self):
        return f"{self.user.email} - {self.date} (Points: {self.points}, Streak: {self.streak})"




class DeviceEvent(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='events')
    event = models.CharField(max_length=50)
    payload = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['device', 'event']),
            models.Index(fields=['created_at']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.device.name} - {self.event} ({self.created_at})"


class DataQualityMetrics(models.Model):
    """Real-time data quality metrics aggregated daily per organization"""
    date = models.DateField(db_index=True)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='quality_metrics')
    total_logs = models.IntegerField(default=0)  # Total logs for the day
    valid_logs = models.IntegerField(default=0)  # Logs with quality_score >= 0.7
    schema_violations = models.IntegerField(default=0)  # Logs that failed schema validation
    avg_data_quality_score = models.FloatField(default=0.0)  # Average quality score
    min_data_quality_score = models.FloatField(default=0.0)
    max_data_quality_score = models.FloatField(default=1.0)
    
    # Distribution metrics for ML analysis
    logs_with_context = models.IntegerField(default=0)  # Logs with non-null context
    avg_idle_ratio = models.FloatField(default=0.0)
    avg_typing_rate_per_min = models.FloatField(default=0.0)
    avg_activity_intensity = models.FloatField(default=0.0)
    
    # Alert flags
    quality_degradation_flag = models.BooleanField(default=False)  # True if avg_quality < 0.75
    high_violation_rate_flag = models.BooleanField(default=False)  # True if violations > 10% of logs
    
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [['date', 'organization']]
        indexes = [
            models.Index(fields=['date', 'organization']),
            models.Index(fields=['organization', 'date']),
            models.Index(fields=['updated_at']),
        ]
        ordering = ['-date']

    def __str__(self):
        return f"{self.organization.name} - {self.date} (Quality: {self.avg_data_quality_score:.2f})"
    
    @property
    def quality_status(self):
        """Human-readable quality status"""
        if self.quality_degradation_flag:
            return "DEGRADED"
        elif self.avg_data_quality_score >= 0.9:
            return "EXCELLENT"
        elif self.avg_data_quality_score >= 0.8:
            return "GOOD"
        elif self.avg_data_quality_score >= 0.7:
            return "FAIR"
        else:
            return "POOR"


# ========================================
# RBAC & PERMISSIONS MODELS
# ========================================

class Role(models.Model):
    """Defines role types within organizations"""
    ROLE_CHOICES = [
        ('owner', 'Owner'),
        ('admin', 'Admin'),
        ('member', 'Member'),
        ('viewer', 'Viewer'),
    ]
    
    name = models.CharField(max_length=50, choices=ROLE_CHOICES, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return self.get_name_display()


class Permission(models.Model):
    """Fine-grained permissions for resources and actions"""
    PERMISSION_CHOICES = [
        # User Management
        ('invite_users', 'Invite Users'),
        ('remove_users', 'Remove Users'),
        ('manage_roles', 'Manage Roles'),
        
        # Data Access
        ('view_own_activity', 'View Own Activity'),
        ('view_team_activity', 'View Team Activity'),
        ('export_own_data', 'Export Own Data'),
        ('export_team_data', 'Export Team Data'),
        
        # Organization Management
        ('manage_org_settings', 'Manage Organization Settings'),
        ('manage_billing', 'Manage Billing'),
        ('manage_modules', 'Manage Modules'),
        
        # Department Management
        ('create_departments', 'Create Departments'),
        ('manage_departments', 'Manage Departments'),
        
        # Advanced
        ('view_audit_logs', 'View Audit Logs'),
        ('manage_api_keys', 'Manage API Keys'),
    ]
    
    name = models.CharField(max_length=50, choices=PERMISSION_CHOICES, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return self.get_name_display()


class RolePermission(models.Model):
    """Maps roles to their permissions"""
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name='role_permissions')
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE)
    
    class Meta:
        unique_together = [['role', 'permission']]
    
    def __str__(self):
        return f"{self.role.name} - {self.permission.name}"


class UserOrgRole(models.Model):
    """Junction table managing user roles within organizations with invitation state"""
    STATE_CHOICES = [
        ('pending', 'Pending'),
        ('invited', 'Invited'),
        ('active', 'Active'),
        ('suspended', 'Suspended'),
        ('inactive', 'Inactive'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='org_roles')
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='user_roles')
    role = models.ForeignKey(Role, on_delete=models.PROTECT)
    state = models.CharField(max_length=20, choices=STATE_CHOICES, default='pending')
    
    # Invitation tracking
    invitation_token = models.CharField(max_length=64, unique=True, null=True, blank=True)
    invitation_expires_at = models.DateTimeField(null=True, blank=True)
    invited_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='invitations_sent')
    invited_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = [['user', 'organization']]
        indexes = [
            models.Index(fields=['organization', 'state']),
            models.Index(fields=['invitation_token']),
            models.Index(fields=['state']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.email} - {self.organization.name} ({self.role.name})"
    
    def generate_invitation_token(self):
        """Generate secure invitation token"""
        self.invitation_token = secrets.token_urlsafe(32)
        self.invitation_expires_at = timezone.now() + timezone.timedelta(days=7)
        self.state = 'invited'
        self.invited_at = timezone.now()
        
    def is_invitation_valid(self):
        """Check if invitation token is still valid"""
        if not self.invitation_token or not self.invitation_expires_at:
            return False
        return timezone.now() < self.invitation_expires_at
    
    def accept_invitation(self):
        """Mark invitation as accepted"""
        self.state = 'active'
        self.accepted_at = timezone.now()
        self.invitation_token = None  # Clear token after use
        self.save()


# ========================================
# DEPARTMENT & HIERARCHY MODELS
# ========================================

class Department(models.Model):
    """Hierarchical department structure within organizations"""
    name = models.CharField(max_length=255)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='departments')
    parent_department = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='sub_departments')
    description = models.TextField(blank=True)
    
    # Manager of this department
    manager = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='managed_departments')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = [['organization', 'name']]
        indexes = [
            models.Index(fields=['organization', 'parent_department']),
        ]
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} ({self.organization.name})"
    
    def get_depth(self):
        """Calculate department depth in hierarchy"""
        depth = 0
        current = self
        while current.parent_department and depth < 10:  # Max depth 10 to prevent infinite loops
            current = current.parent_department
            depth += 1
        return depth
    
    def get_ancestors(self):
        """Get all parent departments up the tree"""
        ancestors = []
        current = self.parent_department
        while current:
            ancestors.append(current)
            current = current.parent_department
        return ancestors
    
    def get_descendants(self):
        """Get all child departments down the tree"""
        descendants = []
        for child in self.sub_departments.all():
            descendants.append(child)
            descendants.extend(child.get_descendants())
        return descendants


class UserDepartment(models.Model):
    """Maps users to departments with role in department"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='department_memberships')
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name='members')
    role_in_department = models.CharField(max_length=100, blank=True)  # e.g., "Lead", "Senior", "Junior"
    
    joined_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = [['user', 'department']]
    
    def __str__(self):
        return f"{self.user.email} - {self.department.name}"


# ========================================
# ORGANIZATION STATE MACHINE
# ========================================

class OrganizationState(models.Model):
    """Tracks organization lifecycle state"""
    STATE_CHOICES = [
        ('created', 'Created'),
        ('active', 'Active'),
        ('suspended', 'Suspended'),
        ('archived', 'Archived'),
    ]
    
    organization = models.OneToOneField(Organization, on_delete=models.CASCADE, related_name='state')
    current_state = models.CharField(max_length=20, choices=STATE_CHOICES, default='created')
    
    # Transition tracking
    previous_state = models.CharField(max_length=20, choices=STATE_CHOICES, null=True, blank=True)
    state_changed_at = models.DateTimeField(null=True, blank=True)
    state_changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Suspension/archive reasons
    reason = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['current_state']),
        ]
    
    def __str__(self):
        return f"{self.organization.name} - {self.current_state}"
    
    def can_transition_to(self, new_state):
        """Validate state transitions"""
        valid_transitions = {
            'created': ['active', 'archived'],
            'active': ['suspended', 'archived'],
            'suspended': ['active', 'archived'],
            'archived': [],  # No transitions from archived
        }
        return new_state in valid_transitions.get(self.current_state, [])
    
    def transition_to(self, new_state, user=None, reason=''):
        """Perform state transition with validation"""
        if not self.can_transition_to(new_state):
            raise ValueError(f"Cannot transition from {self.current_state} to {new_state}")
        
        self.previous_state = self.current_state
        self.current_state = new_state
        self.state_changed_at = timezone.now()
        self.state_changed_by = user
        self.reason = reason
        self.save()


# ========================================
# AUDIT LOGGING
# ========================================

class AuditLog(models.Model):
    """Comprehensive audit trail for all system actions"""
    ACTION_CHOICES = [
        # User actions
        ('user.created', 'User Created'),
        ('user.invited', 'User Invited'),
        ('user.accepted_invitation', 'User Accepted Invitation'),
        ('user.role_changed', 'User Role Changed'),
        ('user.suspended', 'User Suspended'),
        ('user.removed', 'User Removed'),
        
        # Organization actions
        ('org.created', 'Organization Created'),
        ('org.state_changed', 'Organization State Changed'),
        ('org.settings_changed', 'Organization Settings Changed'),
        
        # Permission actions
        ('permission.granted', 'Permission Granted'),
        ('permission.revoked', 'Permission Revoked'),
        
        # Department actions
        ('dept.created', 'Department Created'),
        ('dept.updated', 'Department Updated'),
        ('dept.deleted', 'Department Deleted'),
        
        # Data actions
        ('data.exported', 'Data Exported'),
        ('data.deleted', 'Data Deleted'),
    ]
    
    # Who did it
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_actions')
    actor_email = models.EmailField()  # Store email in case user is deleted
    
    # What happened
    action = models.CharField(max_length=50, choices=ACTION_CHOICES, db_index=True)
    resource_type = models.CharField(max_length=50)  # 'user', 'organization', 'department', etc.
    resource_id = models.IntegerField(null=True, blank=True)
    
    # Context
    organization = models.ForeignKey(Organization, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_logs')
    
    # Changes
    changes_before = models.JSONField(null=True, blank=True)
    changes_after = models.JSONField(null=True, blank=True)
    
    # Metadata
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['organization', 'created_at']),
            models.Index(fields=['actor', 'created_at']),
            models.Index(fields=['action', 'created_at']),
            models.Index(fields=['resource_type', 'resource_id']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.actor_email} - {self.action} ({self.created_at})"


# ========================================
# API KEY MANAGEMENT
# ========================================

class APIKey(models.Model):
    """API keys for programmatic access with scoped permissions"""
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='api_keys')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    name = models.CharField(max_length=255)
    key_prefix = models.CharField(max_length=8)  # First 8 chars for display
    key_hash = models.CharField(max_length=128, unique=True)  # SHA256 hash of full key
    
    # Scopes
    scopes = models.JSONField(default=list)  # e.g., ['read_activity', 'write_activity']
    
    # Status
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['organization', 'is_active']),
            models.Index(fields=['key_hash']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.name} ({self.key_prefix}...)"
    
    @staticmethod
    def generate_key():
        """Generate a new API key"""
        return f"nwata_{secrets.token_urlsafe(32)}"
    
    def verify_key(self, key):
        """Verify a key against the stored hash"""
        key_hash = hashlib.sha256(key.encode()).hexdigest()
        return key_hash == self.key_hash
    
    def is_valid(self):
        """Check if key is active and not expired"""
        if not self.is_active:
            return False
        if self.expires_at and timezone.now() > self.expires_at:
            return False
        return True

    def __str__(self):
        return f"{self.device} - {self.event} @ {self.created_at}"


# ========================================
# NOTIFICATIONS SYSTEM
# ========================================

class Notification(models.Model):
    """In-app notifications for team members about organization events"""
    
    NOTIFICATION_TYPES = (
        ('user_added', 'User Added to Organization'),
        ('user_role_changed', 'User Role Changed'),
        ('user_removed', 'User Removed from Organization'),
        ('user_invited', 'User Invited to Organization'),
        ('invite_accepted', 'Invitation Accepted'),
        ('org_created', 'Organization Created'),
        ('billing_alert', 'Billing Alert'),
        ('security_alert', 'Security Alert'),
    )
    
    # Recipient
    recipient = models.ForeignKey(AuthUser, on_delete=models.CASCADE, related_name='notifications')
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='notifications')
    
    # Notification content
    notification_type = models.CharField(max_length=50, choices=NOTIFICATION_TYPES, db_index=True)
    title = models.CharField(max_length=255)
    message = models.TextField()
    
    # Related data
    actor = models.ForeignKey(AuthUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='notifications_created')
    related_user = models.ForeignKey(AuthUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='notifications_about')
    
    # Extended metadata
    metadata = models.JSONField(default=dict, help_text="Extra data: {'member_name': 'John', 'role': 'admin', etc}")
    
    # Status
    is_read = models.BooleanField(default=False, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Deletion (soft delete)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['recipient', 'is_read', '-created_at']),
            models.Index(fields=['organization', 'is_read', '-created_at']),
            models.Index(fields=['notification_type', '-created_at']),
            models.Index(fields=['recipient', '-created_at']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.title} - {self.recipient.email} ({self.created_at})"
    
    def mark_as_read(self):
        """Mark notification as read"""
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at', 'updated_at'])
    
    def soft_delete(self):
        """Soft delete the notification"""
        if not self.is_deleted:
            self.is_deleted = True
            self.deleted_at = timezone.now()
            self.save(update_fields=['is_deleted', 'deleted_at', 'updated_at'])
    
    @classmethod
    def get_unread_count(cls, user, organization=None):
        """Get count of unread notifications for a user"""
        qs = cls.objects.filter(recipient=user, is_read=False, is_deleted=False)
        if organization:
            qs = qs.filter(organization=organization)
        return qs.count()
    
    @classmethod
    def get_recent(cls, user, organization=None, limit=10):
        """Get recent notifications for a user"""
        qs = cls.objects.filter(recipient=user, is_deleted=False).order_by('-created_at')[:limit]
        if organization:
            qs = qs.filter(organization=organization)
        return qs
