#!/usr/bin/env python
"""
Quick verification of Phase 2 optimizations
"""
import os
import sys
import django
import secrets
from datetime import datetime, timedelta

# Setup Django
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'nwata_web'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'nwata_web.settings')
django.setup()

# Import models and ensure signals are loaded
from api.models import ActivityLog, DataQualityMetrics, Organization, User
from api import signals  # This should register the signals

def test_signal_optimization():
    """Test that the optimized signal works correctly"""
    print("Testing optimized data quality signal...")

    # Create test organization with unique subdomain
    random_suffix = secrets.token_hex(4)
    org = Organization.objects.create(
        name=f"Test Org {random_suffix}",
        subdomain=f"test-org-{random_suffix}"
    )

    # Create test user with unique email
    user = User.objects.create(
        email=f"test{random_suffix}@example.com",
        org=org
    )

    # Create test activity logs
    now = datetime.now()
    logs_data = [
        {
            'start_time': now - timedelta(minutes=10),
            'end_time': now - timedelta(minutes=5),
            'app_name': 'vscode',
            'window_title': 'test.py',
            'category': 'coding',
            'context': {
                'typing_count': 300,
                'scroll_count': 50,
                'shortcut_count': 10,
                'total_idle_ms': 60000,  # 1 minute idle
                'max_idle_ms': 30000,
                'window_duration_s': 300.0,  # 5 minutes
                'typing_rate_per_min': 50.0
            },
            # Don't set data_quality_score - let the model compute it
            'validation_errors': None
        },
        {
            'start_time': now - timedelta(minutes=5),
            'end_time': now,
            'app_name': 'chrome',
            'window_title': 'example.com',
            'category': 'browsing',
            'context': {
                'typing_count': 50,
                'scroll_count': 200,
                'shortcut_count': 5,
                'total_idle_ms': 120000,  # 2 minutes idle
                'max_idle_ms': 60000,
                'window_duration_s': 300.0,  # 5 minutes
                'typing_rate_per_min': 10.0
            },
            # Don't set data_quality_score - let the model compute it
            'validation_errors': None
        }
    ]

    # Create logs (this should trigger the signal)
    logs = []
    for data in logs_data:
        log = ActivityLog.objects.create(user=user, **data)
        logs.append(log)

    # Check that metrics were created/updated
    metrics = DataQualityMetrics.objects.filter(
        date=now.date(),
        organization=org
    ).first()

    if not metrics:
        print("❌ FAIL: No metrics created")
        return False

    print(f"✅ Metrics created: total_logs={metrics.total_logs}, avg_quality={metrics.avg_data_quality_score}")

    # Verify calculations
    expected_avg_quality = 1.0  # Both logs get perfect scores
    if abs(metrics.avg_data_quality_score - expected_avg_quality) > 0.01:
        print(f"❌ FAIL: Expected avg quality {expected_avg_quality}, got {metrics.avg_data_quality_score}")
        return False

    if metrics.total_logs != 2:
        print(f"❌ FAIL: Expected 2 total logs, got {metrics.total_logs}")
        return False

    if metrics.valid_logs != 2:  # Both should be valid (>= 0.7)
        print(f"❌ FAIL: Expected 2 valid logs, got {metrics.valid_logs}")
        return False

    # Test with a low quality log
    ActivityLog.objects.create(
        user=user,
        start_time=now - timedelta(minutes=2),
        end_time=now - timedelta(minutes=1),
        app_name='unknown',
        window_title='error page',
        category='unknown',
        context=None,
        data_quality_score=0.3,  # Manually set low score
        validation_errors=['Missing context']
    )

    # Refresh metrics
    metrics.refresh_from_db()

    if metrics.total_logs != 3:
        print(f"❌ FAIL: Expected 3 total logs after adding low quality log, got {metrics.total_logs}")
        return False

    if metrics.valid_logs != 2:  # Still only 2 valid
        print(f"❌ FAIL: Expected 2 valid logs after adding low quality log, got {metrics.valid_logs}")
        return False

    if metrics.schema_violations != 1:
        print(f"❌ FAIL: Expected 1 schema violation, got {metrics.schema_violations}")
        return False

    print("✅ All signal optimization tests passed!")
    return True

if __name__ == '__main__':
    try:
        success = test_signal_optimization()
        if success:
            print("\n🎉 Phase 2 signal optimization verification complete!")
            sys.exit(0)
        else:
            print("\n❌ Signal optimization tests failed!")
            sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)