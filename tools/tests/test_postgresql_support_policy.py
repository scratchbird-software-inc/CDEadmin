"""The PostgreSQL admission policy follows the project's support policy."""
import sys
import unittest
from datetime import date
from pathlib import Path

WEB = Path(__file__).resolve().parents[2] / 'web'
if str(WEB) not in sys.path:
    sys.path.insert(0, str(WEB))

from pgadmin.cdeadmin.providers.postgresql import (  # noqa: E402
    support_policy as policy,
)


class SupportTableTests(unittest.TestCase):
    def test_every_major_has_five_years_of_support_ending_in_november(self):
        # https://www.postgresql.org/support/versioning/: five years of
        # minor releases, the final one in the November five years after
        # the initial release.
        for major, (initial, final) in policy.SUPPORTED_MAJORS.items():
            self.assertEqual(final.year, initial.year + 5, major)
            self.assertEqual(final.month, 11, major)
            self.assertLess(initial, final, major)

    def test_majors_are_contiguous_and_dated_in_order(self):
        majors = sorted(policy.SUPPORTED_MAJORS)
        self.assertEqual(majors, list(range(majors[0], majors[-1] + 1)))
        initials = [policy.SUPPORTED_MAJORS[m][0] for m in majors]
        self.assertEqual(initials, sorted(initials))

    def test_policy_snapshot_is_dated(self):
        self.assertIsInstance(policy.POLICY_READ_ON, date)
        # A snapshot older than its newest major's support window would
        # admit versions the project may have retired.
        newest_final = max(f for (_i, f) in policy.SUPPORTED_MAJORS.values())
        self.assertLess(policy.POLICY_READ_ON, newest_final)


class VersionReadingTests(unittest.TestCase):
    def test_reads_libpq_integers_and_public_text(self):
        self.assertEqual((18, 3), policy.runtime_major_minor(180003))
        self.assertEqual((16, 15), policy.runtime_major_minor(160015))
        self.assertEqual((18, 3), policy.runtime_major_minor('18.3'))
        self.assertEqual((14, 0), policy.runtime_major_minor('14'))
        self.assertEqual('16.15', policy.public_version(160015))

    def test_unreadable_values_are_reported_not_guessed(self):
        self.assertIsNone(policy.runtime_major_minor('latest'))
        self.assertIsNone(policy.runtime_major_minor(True))
        self.assertIsNone(policy.runtime_major_minor(90605))
        self.assertEqual('unreadable', policy.support_state('latest'))


class AdmissionTests(unittest.TestCase):
    TODAY = date(2026, 11, 10)

    def test_admits_every_version_the_project_supports_today(self):
        for version in (140000, '14.20', 150000, 160015, 170006, 180003,
                        180004, '18.9'):
            self.assertIsNone(policy.admission_error(version, self.TODAY),
                              version)

    def test_refuses_a_major_past_its_final_release(self):
        error = policy.admission_error(130022, self.TODAY)
        self.assertIn('13.22', error)
        self.assertIn('no longer supported', error)
        self.assertIn('2025-11-13', error)

    def test_the_window_closes_on_the_final_release_date(self):
        final = policy.SUPPORTED_MAJORS[14][1]
        self.assertEqual('supported', policy.support_state(140020, final))
        day_after = date(final.year, final.month, final.day + 1)
        self.assertEqual('end_of_life',
                         policy.support_state(140020, day_after))

    def test_a_major_outside_the_table_is_refused_with_the_snapshot_date(self):
        error = policy.admission_error(190000, self.TODAY)
        self.assertIn('19.0', error)
        self.assertIn('2026-11-10', error)
        self.assertIn('support_policy.py', error)
        self.assertIn('12.22', policy.admission_error(120022, self.TODAY))


if __name__ == '__main__':
    unittest.main()
