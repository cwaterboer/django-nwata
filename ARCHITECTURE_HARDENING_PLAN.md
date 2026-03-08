# Nwata Architecture Hardening & ML Foundation Plan

## Executive Summary

This execution plan addresses critical gaps in Nwata's data architecture to prepare for ML-driven feedback loops. The plan focuses on data validation, quality monitoring, and scalable ETL foundations while maintaining backward compatibility.

**Timeline**: 6 weeks  
**Risk Level**: Medium (incremental changes with rollback capability)  
**Success Criteria**: 90%+ data quality scores, validated ML-ready features, comprehensive monitoring

## Phase 1: Core Data Validation (Week 1-2)

### Objective
Implement robust data validation and quality scoring to prevent invalid data from entering the system.

### Tasks

#### 1.1 Schema Validation Framework
**Deliverables**:
- JSON Schema definitions for context data
- Validation functions in `api/models.py`
- Unit tests for schema validation

**Implementation**:
```python
# Add to api/models.py
import jsonschema
from jsonschema import validate, ValidationError

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
```

**Dependencies**: None  
**Owner**: Backend Developer  
**Testing**: Unit tests with valid/invalid context samples

#### 1.2 Database Schema Enhancement
**Deliverables**:
- Migration adding quality tracking fields
- Updated ActivityLog model with validation
- Data quality computation methods

**Implementation**:
```python
# Migration: 0007_data_quality_fields.py
class Migration(migrations.Migration):
    operations = [
        migrations.AddField(
            model_name='activitylog',
            name='context_schema_version',
            field=models.CharField(default='1.0', max_length=10),
        ),
        migrations.AddField(
            model_name='activitylog',
            name='data_quality_score',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='activitylog',
            name='normalized_context',
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='activitylog',
            name='validation_errors',
            field=models.JSONField(blank=True, null=True),
        ),
    ]
```

**Dependencies**: Schema validation framework  
**Owner**: Backend Developer  
**Testing**: Migration testing, model validation

#### 1.3 API Validation Upgrade
**Deliverables**:
- Enhanced `ActivityIngest._validate_log_entry()`
- Context validation integration
- Improved error responses

**Implementation**:
```python
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
    
    return len(errors) == 0, errors, warnings
```

**Dependencies**: Schema validation framework  
**Owner**: Backend Developer  
**Testing**: API integration tests with various payloads

### Phase 1 Success Criteria
- ✅ All context data validated against schema
- ✅ 100% of new ActivityLog entries have quality scores
- ✅ API rejects invalid context data with clear error messages
- ✅ Backward compatibility maintained for existing data

## Phase 2: ML Feature Engineering (Week 3-4)

### Objective
Create normalized, ML-ready features and establish data quality monitoring.

### Tasks

#### 2.1 Feature Normalization Pipeline
**Deliverables**:
- `normalize_context_for_ml()` function
- Normalized features in ActivityLog model
- Feature engineering documentation

**Implementation**:
```python
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
```

**Dependencies**: Database schema enhancement  
**Owner**: Data Engineer  
**Testing**: Feature distribution analysis, normalization validation

#### 2.2 Data Quality Monitoring System
**Deliverables**:
- DataQualityMetrics model and signals
- Daily quality aggregation
- Quality dashboard endpoints

**Implementation**:
```python
class DataQualityMetrics(models.Model):
    date = models.DateField()
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    total_logs = models.IntegerField()
    valid_logs = models.IntegerField()
    schema_violations = models.IntegerField()
    avg_data_quality_score = models.FloatField()
    
    class Meta:
        unique_together = [('date', 'organization')]

# Signal for real-time updates
@receiver(post_save, sender=ActivityLog)
def update_data_quality_metrics(sender, instance, created, **kwargs):
    # Implementation for daily aggregation
```

**Dependencies**: Database schema enhancement  
**Owner**: Backend Developer  
**Testing**: Signal firing tests, aggregation accuracy

#### 2.3 Agent-Side Data Quality Improvements
**Deliverables**:
- Enhanced `ContextSignals.finalize()` method
- Bounds checking and validation
- Additional ML-ready features

**Implementation**:
```python
# In nwata_min.py
def finalize(self, window_duration_s):
    """Enhanced finalization with validation and ML features"""
    context = {
        "typing_count": max(0, self.typing_count),
        "scroll_count": max(0, self.scroll_count),
        "shortcut_count": max(0, self.shortcut_count),
        "total_idle_ms": max(0, int(self.total_idle_ms)),
        "max_idle_ms": max(0, int(self.max_idle_ms)),
        "window_duration_s": max(0.001, window_duration_s),
    }
    
    # Derived metrics with bounds
    duration_min = context["window_duration_s"] / 60
    context["typing_rate_per_min"] = round(min(self.typing_count / duration_min, 1000), 2)
    context["scroll_rate_per_min"] = round(min(self.scroll_count / duration_min, 500), 2)
    
    # ML-ready features
    context["activity_events_total"] = (
        context["typing_count"] + context["scroll_count"] + context["shortcut_count"]
    )
    context["idle_ratio"] = min(context["total_idle_ms"] / (context["window_duration_s"] * 1000), 1.0)
    
    return context
```

**Dependencies**: None (can be done in parallel)  
**Owner**: Agent Developer  
**Testing**: Agent unit tests, data consistency checks

### Phase 2 Success Criteria
- ✅ All ActivityLog entries have normalized_context populated
- ✅ Data quality metrics updated in real-time
- ✅ Agent produces validated, ML-ready context data
- ✅ Feature distributions analyzed and documented

## Phase 3: ETL Pipeline & Advanced Monitoring (Week 5-6)

### Objective
Build scalable ETL infrastructure and comprehensive monitoring for production ML workflows.

### Tasks

#### 3.1 ETL Processing Framework
**Deliverables**:
- `process_ml_data` management command
- Data extraction and cleaning pipeline
- ML-ready dataset generation

**Implementation**:
```python
# api/management/commands/process_ml_data.py
class Command(BaseCommand):
    help = 'Extract and process activity data for ML training'
    
    def handle(self, *args, **options):
        # Extract high-quality data
        queryset = ActivityLog.objects.filter(
            data_quality_score__gte=0.8,
            normalized_context__isnull=False
        )
        
        # Convert to DataFrame and save as Parquet
        data = []
        for log in queryset:
            row = {
                'user_id': log.user.id,
                'app_name': log.app_name,
                'duration': log.duration,
                'data_quality_score': log.data_quality_score,
                **log.normalized_context
            }
            data.append(row)
        
        df = pd.DataFrame(data)
        output_path = f'/tmp/ml_data_{timezone.now().date()}.parquet'
        df.to_parquet(output_path)
        
        self.stdout.write(f'Processed {len(df)} records to {output_path}')
```

**Dependencies**: Feature normalization pipeline  
**Owner**: Data Engineer  
**Testing**: End-to-end pipeline tests, data quality validation

#### 3.2 API Rate Limiting & Security
**Deliverables**:
- Request rate limiting (1000 logs/min per device)
- Payload size validation (max 10KB per log)
- Enhanced authentication checks

**Implementation**:
```python
# In api/views.py
from django_ratelimit.decorators import ratelimit

class ActivityIngest(DeviceAuthMixin, APIView):
    @method_decorator(ratelimit(key='user', rate='1000/m', method='POST'))
    def post(self, request):
        # Rate limiting by device token
        
        # Payload size check
        if len(request.body) > 10240:  # 10KB limit
            return Response({"error": "Payload too large"}, status=413)
```

**Dependencies**: API validation upgrade  
**Owner**: Backend Developer  
**Testing**: Load testing, security validation

#### 3.3 Monitoring Dashboard Integration
**Deliverables**:
- Quality metrics in dashboard views
- Alert system for data quality issues
- Data health visualization

**Implementation**:
```python
# In dashboard/views.py
def dashboard(request):
    # ... existing code ...
    
    # Add data quality metrics
    today = datetime.now().date()
    quality_metrics = DataQualityMetrics.objects.filter(
        date=today,
        organization=org
    ).first()
    
    context.update({
        'data_quality_score': quality_metrics.avg_data_quality_score if quality_metrics else None,
        'total_valid_logs': quality_metrics.valid_logs if quality_metrics else 0,
        'schema_violations': quality_metrics.schema_violations if quality_metrics else 0,
    })
```

**Dependencies**: Data quality monitoring system  
**Owner**: Frontend Developer  
**Testing**: Dashboard integration tests

### Phase 3 Success Criteria
- ✅ Automated ETL pipeline generates clean ML datasets
- ✅ API protected against abuse with rate limiting
- ✅ Data quality visible in dashboard
- ✅ Alert system for quality degradation

## Risk Mitigation

### Technical Risks
- **Data Migration Issues**: Test migrations on staging environment first
- **Backward Compatibility**: Maintain null-safe operations for existing data
- **Performance Impact**: Monitor query performance, add database indexes as needed

### Operational Risks
- **Agent Compatibility**: Version negotiation for schema updates
- **Data Loss Prevention**: Comprehensive backups before schema changes
- **Rollback Strategy**: Feature flags for incremental deployment

### Testing Strategy

#### Unit Testing
- Schema validation functions
- Data quality computation
- Feature normalization logic

#### Integration Testing
- API validation with various payloads
- Database migrations with existing data
- ETL pipeline end-to-end

#### Load Testing
- API rate limiting under high load
- Database performance with quality computations
- Agent sync with large context payloads

#### Data Quality Testing
- Statistical analysis of normalized features
- Outlier detection validation
- ML model training with processed data

## Success Metrics

### Quantitative
- **Data Quality Score**: ≥90% of logs with score ≥0.8
- **Schema Compliance**: 100% of new logs pass validation
- **API Uptime**: 99.9% during implementation
- **Processing Performance**: ETL completes within 30 minutes for 1M records

### Qualitative
- **ML Readiness**: Consistent feature distributions for model training
- **Monitoring Coverage**: Real-time visibility into data health
- **Developer Experience**: Clear error messages and validation feedback

## Resource Requirements

### Team
- **Backend Developer**: 2 FTE (API, database, monitoring)
- **Data Engineer**: 1 FTE (ETL, feature engineering)
- **Agent Developer**: 0.5 FTE (client-side improvements)
- **QA Engineer**: 1 FTE (testing, validation)

### Infrastructure
- **Staging Environment**: Full copy for testing
- **Monitoring Tools**: Data quality dashboards
- **CI/CD Pipeline**: Automated testing for all changes

## Communication Plan

### Weekly Check-ins
- Progress updates and blocker resolution
- Demo of completed features
- Risk assessment and mitigation

### Documentation
- Updated API specifications
- Data schema documentation
- ML feature engineering guide

### Stakeholder Updates
- Bi-weekly progress reports
- Go-live readiness assessment
- Post-implementation review

## Go-Live Checklist

- [ ] All migrations tested on staging
- [ ] Backward compatibility verified
- [ ] Data quality monitoring active
- [ ] ETL pipeline operational
- [ ] API rate limiting configured
- [ ] Agent updates deployed
- [ ] Dashboard quality metrics visible
- [ ] Monitoring alerts configured
- [ ] Rollback procedures documented

This plan provides a systematic approach to hardening Nwata's architecture while building a solid foundation for ML-driven productivity insights. The phased approach minimizes risk while delivering incremental value.</content>
<parameter name="filePath">/workspaces/django-nwata/ARCHITECTURE_HARDENING_PLAN.md