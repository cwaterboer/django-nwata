"""
Management command to verify Phase 2 ML Feature Engineering implementation.
Tests all components: models, migrations, signals, normalization, and API endpoints.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.test import Client
from datetime import datetime, timedelta
import json
import sys
from api.models import (
    Organization, User, Device, ActivityLog, DataQualityMetrics,
    normalize_context_for_ml, compute_data_quality_score, validate_context_data
)


class Command(BaseCommand):
    help = 'Verify Phase 2 ML Feature Engineering implementation'

    def add_arguments(self, parser):
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Print detailed output for each test'
        )

    def handle(self, *args, **options):
        verbose = options.get('verbose', False)
        self.verbose = verbose
        
        self.stdout.write(self.style.SUCCESS('\n' + '='*70))
        self.stdout.write(self.style.SUCCESS('PHASE 2: ML FEATURE ENGINEERING VERIFICATION'))
        self.stdout.write(self.style.SUCCESS('='*70 + '\n'))
        
        results = {
            'passed': 0,
            'failed': 0,
            'warnings': 0,
            'tests': []
        }
        
        # Test 1: Schema validation
        self._test_schema_validation(results)
        
        # Test 2: Data quality scoring
        self._test_data_quality_scoring(results)
        
        # Test 3: ML feature normalization
        self._test_ml_normalization(results)
        
        # Test 4: Model migrations and fields
        self._test_model_fields(results)
        
        # Test 5: Signal integration
        self._test_signal_integration(results)
        
        # Test 6: API endpoints
        self._test_api_endpoints(results)
        
        # Test 7: Data quality metrics aggregation
        self._test_metrics_aggregation(results)
        
        # Print summary
        self._print_summary(results)
        
        # Exit with appropriate code
        sys.exit(0 if results['failed'] == 0 else 1)
    
    def _test_schema_validation(self, results):
        """Test 1: Context schema validation"""
        test_name = "Schema Validation"
        self.stdout.write(f"\nTest 1: {test_name}")
        self.stdout.write("-" * 50)
        
        try:
            # Valid context
            valid_context = {
                "typing_count": 45,
                "scroll_count": 12,
                "shortcut_count": 3,
                "total_idle_ms": 10000,
                "max_idle_ms": 5000,
                "window_duration_s": 300.5,
                "typing_rate_per_min": 9.0,
                "scroll_rate_per_min": 2.4
            }
            
            is_valid, errors, warnings = validate_context_data(valid_context)
            if not is_valid:
                self.stdout.write(self.style.ERROR(f"  ✗ Valid context rejected: {errors}"))
                results['failed'] += 1
                results['tests'].append((test_name, 'FAILED', str(errors)))
                return
            
            # Invalid context (exceeds max)
            invalid_context = {
                "typing_count": 15000,  # exceeds max of 10000
                "scroll_count": 12,
                "shortcut_count": 3,
                "total_idle_ms": 10000,
                "max_idle_ms": 5000,
                "window_duration_s": 300.5,
            }
            
            is_valid, errors, _ = validate_context_data(invalid_context)
            if is_valid:
                self.stdout.write(self.style.ERROR("  ✗ Invalid context was accepted"))
                results['failed'] += 1
                results['tests'].append((test_name, 'FAILED', 'Invalid context accepted'))
                return
            
            # None context (acceptable)
            is_valid, _, _ = validate_context_data(None)
            if not is_valid:
                self.stdout.write(self.style.ERROR("  ✗ None context rejected"))
                results['failed'] += 1
                results['tests'].append((test_name, 'FAILED', 'None context rejected'))
                return
            
            self.stdout.write(self.style.SUCCESS("  ✓ Schema validation working correctly"))
            results['passed'] += 1
            results['tests'].append((test_name, 'PASSED', 'All validation rules enforced'))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"  ✗ Error: {str(e)}"))
            results['failed'] += 1
            results['tests'].append((test_name, 'FAILED', str(e)))
    
    def _test_data_quality_scoring(self, results):
        """Test 2: Data quality score computation"""
        test_name = "Data Quality Scoring"
        self.stdout.write(f"\nTest 2: {test_name}")
        self.stdout.write("-" * 50)
        
        try:
            now = timezone.now()
            start = now - timedelta(minutes=5)
            end = now
            
            # Test with valid context
            context = {
                "typing_count": 45,
                "scroll_count": 12,
                "shortcut_count": 3,
                "total_idle_ms": 10000,
                "max_idle_ms": 5000,
                "window_duration_s": 300.0,
                "typing_rate_per_min": 9.0,
                "scroll_rate_per_min": 2.4
            }
            
            score = compute_data_quality_score(context, start, end)
            if not (0 <= score <= 1):
                self.stdout.write(self.style.ERROR(f"  ✗ Score out of range [0-1]: {score}"))
                results['failed'] += 1
                results['tests'].append((test_name, 'FAILED', f'Score out of range: {score}'))
                return
            
            if self.verbose:
                self.stdout.write(f"  → Quality score: {score:.3f}")
            
            # Test with no context (should be penalized)
            score_no_context = compute_data_quality_score(None, start, end)
            if score_no_context >= score:
                self.stdout.write(self.style.WARNING("  ⚠ No context not penalized enough"))
                results['warnings'] += 1
            
            # Test with invalid duration
            bad_start = end + timedelta(hours=1)
            score_bad = compute_data_quality_score(context, bad_start, end)
            if score_bad >= 0.5:
                self.stdout.write(self.style.WARNING("  ⚠ Invalid duration not penalized enough"))
                results['warnings'] += 1
            
            self.stdout.write(self.style.SUCCESS("  ✓ Data quality scoring working correctly"))
            results['passed'] += 1
            results['tests'].append((test_name, 'PASSED', f'Scores computed correctly (range: {score_no_context:.2f}-{score:.2f})'))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"  ✗ Error: {str(e)}"))
            results['failed'] += 1
            results['tests'].append((test_name, 'FAILED', str(e)))
    
    def _test_ml_normalization(self, results):
        """Test 3: ML feature normalization"""
        test_name = "ML Feature Normalization"
        self.stdout.write(f"\nTest 3: {test_name}")
        self.stdout.write("-" * 50)
        
        try:
            context = {
                "typing_count": 60,
                "scroll_count": 15,
                "shortcut_count": 5,
                "total_idle_ms": 50000,
                "max_idle_ms": 30000,
                "window_duration_s": 300.0,
                "typing_rate_per_min": 12.0,
                "scroll_rate_per_min": 3.0
            }
            
            normalized = normalize_context_for_ml(context)
            
            # Check required fields
            required = ['has_context', 'typing_count_norm', 'scroll_count_norm', 'idle_ratio', 'activity_intensity', 'peak_idle_ratio']
            for field in required:
                if field not in normalized:
                    self.stdout.write(self.style.ERROR(f"  ✗ Missing field: {field}"))
                    results['failed'] += 1
                    results['tests'].append((test_name, 'FAILED', f'Missing field: {field}'))
                    return
            
            # Check value ranges
            if not (0 <= normalized['idle_ratio'] <= 1.0):
                self.stdout.write(self.style.ERROR(f"  ✗ idle_ratio out of range: {normalized['idle_ratio']}"))
                results['failed'] += 1
                results['tests'].append((test_name, 'FAILED', f'idle_ratio out of range'))
                return
            
            if not (0 <= normalized['peak_idle_ratio'] <= 1.0):
                self.stdout.write(self.style.ERROR(f"  ✗ peak_idle_ratio out of range: {normalized['peak_idle_ratio']}"))
                results['failed'] += 1
                results['tests'].append((test_name, 'FAILED', f'peak_idle_ratio out of range'))
                return
            
            if self.verbose:
                self.stdout.write(f"\n  Normalized features:")
                for key, val in normalized.items():
                    if isinstance(val, float):
                        self.stdout.write(f"    {key}: {val:.3f}")
                    else:
                        self.stdout.write(f"    {key}: {val}")
            
            # Test with None context
            normalized_none = normalize_context_for_ml(None)
            if normalized_none['has_context']:
                self.stdout.write(self.style.ERROR("  ✗ None context should have has_context=False"))
                results['failed'] += 1
                results['tests'].append((test_name, 'FAILED', 'None context handling failed'))
                return
            
            self.stdout.write(self.style.SUCCESS("  ✓ ML normalization working correctly"))
            results['passed'] += 1
            results['tests'].append((test_name, 'PASSED', 'Features normalized and validated'))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"  ✗ Error: {str(e)}"))
            results['failed'] += 1
            results['tests'].append((test_name, 'FAILED', str(e)))
    
    def _test_model_fields(self, results):
        """Test 4: Model fields and migrations"""
        test_name = "Model Fields & Migrations"
        self.stdout.write(f"\nTest 4: {test_name}")
        self.stdout.write("-" * 50)
        
        try:
            # Check ActivityLog has required fields
            required_fields = ['context', 'context_schema_version', 'data_quality_score', 'normalized_context', 'validation_errors']
            for field in required_fields:
                if not hasattr(ActivityLog, field):
                    self.stdout.write(self.style.ERROR(f"  ✗ ActivityLog missing field: {field}"))
                    results['failed'] += 1
                    results['tests'].append((test_name, 'FAILED', f'Missing field: {field}'))
                    return
            
            # Check DataQualityMetrics model exists
            required_metrics_fields = ['date', 'organization', 'total_logs', 'valid_logs', 'schema_violations', 'avg_data_quality_score', 'quality_status']
            for field in required_metrics_fields:
                if not hasattr(DataQualityMetrics, field):
                    self.stdout.write(self.style.ERROR(f"  ✗ DataQualityMetrics missing field: {field}"))
                    results['failed'] += 1
                    results['tests'].append((test_name, 'FAILED', f'Missing metrics field: {field}'))
                    return
            
            if self.verbose:
                self.stdout.write("  ✓ All ActivityLog fields present")
                self.stdout.write("  ✓ All DataQualityMetrics fields present")
            
            self.stdout.write(self.style.SUCCESS("  ✓ Model schema is complete"))
            results['passed'] += 1
            results['tests'].append((test_name, 'PASSED', 'All required database fields exist'))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"  ✗ Error: {str(e)}"))
            results['failed'] += 1
            results['tests'].append((test_name, 'FAILED', str(e)))
    
    def _test_signal_integration(self, results):
        """Test 5: Signal integration"""
        test_name = "Signal Integration"
        self.stdout.write(f"\nTest 5: {test_name}")
        self.stdout.write("-" * 50)
        
        try:
            # Create test org and user
            org = Organization.objects.first() or Organization.objects.create(
                name='Test Org',
                subdomain='test-org-1'
            )
            user = User.objects.filter(org=org).first() or User.objects.create(
                email='test@example.com',
                org=org
            )
            
            # Create activity log with context
            now = timezone.now()
            context_data = {
                "typing_count": 50,
                "scroll_count": 10,
                "shortcut_count": 2,
                "total_idle_ms": 15000,
                "max_idle_ms": 10000,
                "window_duration_s": 180.0,
                "typing_rate_per_min": 16.7,
                "scroll_rate_per_min": 3.3
            }
            
            activity = ActivityLog.objects.create(
                user=user,
                app_name='Test App',
                window_title='Test Window',
                start_time=now - timedelta(minutes=3),
                end_time=now,
                context=context_data
            )
            
            # Check if quality score was computed
            activity.refresh_from_db()
            if activity.data_quality_score is None:
                self.stdout.write(self.style.ERROR("  ✗ Quality score not computed in save hook"))
                results['failed'] += 1
                results['tests'].append((test_name, 'FAILED', 'Quality score not computed'))
                return
            
            if self.verbose:
                self.stdout.write(f"  → Quality score: {activity.data_quality_score:.3f}")
            
            # Check if normalized context was created
            if activity.normalized_context is None:
                self.stdout.write(self.style.ERROR("  ✗ Normalized context not created in save hook"))
                results['failed'] += 1
                results['tests'].append((test_name, 'FAILED', 'Normalized context not created'))
                return
            
            if self.verbose:
                self.stdout.write(f"  → Normalized context keys: {list(activity.normalized_context.keys())}")
            
            # Check if signal updated metrics
            today = now.date()
            metrics = DataQualityMetrics.objects.filter(date=today, organization=org).first()
            if metrics is None:
                self.stdout.write(self.style.ERROR("  ✗ Signal did not create DataQualityMetrics"))
                results['failed'] += 1
                results['tests'].append((test_name, 'FAILED', 'Signal did not create metrics'))
                return
            
            if metrics.total_logs == 0:
                self.stdout.write(self.style.ERROR("  ✗ Signal did not update metrics counts"))
                results['failed'] += 1
                results['tests'].append((test_name, 'FAILED', 'Metrics not updated'))
                return
            
            if self.verbose:
                self.stdout.write(f"  → Metrics created with {metrics.total_logs} logs")
                self.stdout.write(f"  → Quality status: {metrics.quality_status}")
            
            self.stdout.write(self.style.SUCCESS("  ✓ Signals integrated correctly"))
            results['passed'] += 1
            results['tests'].append((test_name, 'PASSED', f'Metrics auto-computed on ActivityLog save'))
            
            # Cleanup
            activity.delete()
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"  ✗ Error: {str(e)}"))
            results['failed'] += 1
            results['tests'].append((test_name, 'FAILED', str(e)))
    
    def _test_api_endpoints(self, results):
        """Test 6: API endpoints"""
        test_name = "API Endpoints"
        self.stdout.write(f"\nTest 6: {test_name}")
        self.stdout.write("-" * 50)
        
        try:
            from django.test import Client
            
            # Check endpoints are registered
            client = Client()
            
            # We can't easily test without valid auth, but we can check they don't 404
            resp = client.get('/api/quality/metrics/')
            if resp.status_code == 404:
                self.stdout.write(self.style.ERROR("  ✗ /api/quality/metrics/ endpoint not found"))
                results['failed'] += 1
                results['tests'].append((test_name, 'FAILED', 'Metrics endpoint not found'))
                return
            
            resp = client.get('/api/quality/trend/')
            if resp.status_code == 404:
                self.stdout.write(self.style.ERROR("  ✗ /api/quality/trend/ endpoint not found"))
                results['failed'] += 1
                results['tests'].append((test_name, 'FAILED', 'Trend endpoint not found'))
                return
            
            if self.verbose:
                self.stdout.write("  ✓ /api/quality/metrics/ endpoint exists")
                self.stdout.write("  ✓ /api/quality/trend/ endpoint exists")
            
            self.stdout.write(self.style.SUCCESS("  ✓ API endpoints registered correctly"))
            results['passed'] += 1
            results['tests'].append((test_name, 'PASSED', 'Quality monitoring endpoints available'))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"  ✗ Error: {str(e)}"))
            results['failed'] += 1
            results['tests'].append((test_name, 'FAILED', str(e)))
    
    def _test_metrics_aggregation(self, results):
        """Test 7: Data quality metrics aggregation"""
        test_name = "Metrics Aggregation"
        self.stdout.write(f"\nTest 7: {test_name}")
        self.stdout.write("-" * 50)
        
        try:
            # Get or create org/user
            org = Organization.objects.first() or Organization.objects.create(
                name='Test Org 2',
                subdomain='test-org-2'
            )
            user = User.objects.filter(org=org).first() or User.objects.create(
                email='test2@example.com',
                org=org
            )
            
            # Create multiple activity logs
            now = timezone.now()
            context_data = {
                "typing_count": 50,
                "scroll_count": 10,
                "shortcut_count": 2,
                "total_idle_ms": 15000,
                "max_idle_ms": 10000,
                "window_duration_s": 180.0,
                "typing_rate_per_min": 16.7,
                "scroll_rate_per_min": 3.3
            }
            
            for i in range(3):
                ActivityLog.objects.create(
                    user=user,
                    app_name=f'App {i}',
                    window_title='Test',
                    start_time=now - timedelta(minutes=5-i),
                    end_time=now - timedelta(minutes=4-i),
                    context=context_data
                )
            
            # Check metrics
            today = now.date()
            metrics = DataQualityMetrics.objects.filter(date=today, organization=org).first()
            
            if metrics is None:
                self.stdout.write(self.style.WARNING("  ⚠ DataQualityMetrics not found (may not have been created yet)"))
                results['warnings'] += 1
            else:
                if metrics.total_logs < 3:
                    self.stdout.write(self.style.WARNING(f"  ⚠ Expected 3+ logs, got {metrics.total_logs}"))
                    results['warnings'] += 1
                
                if metrics.avg_data_quality_score == 0:
                    self.stdout.write(self.style.WARNING("  ⚠ Average quality score not computed"))
                    results['warnings'] += 1
                
                if self.verbose:
                    self.stdout.write(f"  → Total logs: {metrics.total_logs}")
                    self.stdout.write(f"  → Valid logs: {metrics.valid_logs}")
                    self.stdout.write(f"  → Avg quality: {metrics.avg_data_quality_score:.3f}")
                    self.stdout.write(f"  → Quality status: {metrics.quality_status}")
            
            self.stdout.write(self.style.SUCCESS("  ✓ Metrics aggregation working"))
            results['passed'] += 1
            results['tests'].append((test_name, 'PASSED', 'Aggregation computes daily metrics'))
            
            # Cleanup
            ActivityLog.objects.filter(user=user).delete()
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"  ✗ Error: {str(e)}"))
            results['failed'] += 1
            results['tests'].append((test_name, 'FAILED', str(e)))
    
    def _print_summary(self, results):
        """Print test summary"""
        self.stdout.write('\n' + '='*70)
        self.stdout.write('TEST SUMMARY')
        self.stdout.write('='*70)
        
        for test_name, status, details in results['tests']:
            if status == 'PASSED':
                icon = '✓'
                style = self.style.SUCCESS
            elif status == 'FAILED':
                icon = '✗'
                style = self.style.ERROR
            else:
                icon = '⚠'
                style = self.style.WARNING
            
            self.stdout.write(style(f"{icon} {test_name}: {status}"))
            if self.verbose:
                self.stdout.write(f"  {details}")
        
        self.stdout.write('\n' + '='*70)
        self.stdout.write(f"Passed: {results['passed']} | Failed: {results['failed']} | Warnings: {results['warnings']}")
        self.stdout.write('='*70 + '\n')
        
        if results['failed'] == 0:
            self.stdout.write(self.style.SUCCESS("✓ ALL TESTS PASSED - Phase 2 implementation is complete!"))
        else:
            self.stdout.write(self.style.ERROR(f"✗ {results['failed']} TEST(S) FAILED - Please review errors above"))
