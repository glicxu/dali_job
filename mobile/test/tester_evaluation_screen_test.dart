import 'dart:convert';

import 'package:dalijob_mobile/src/api/api_client.dart';
import 'package:dalijob_mobile/src/auth/auth_repository.dart';
import 'package:dalijob_mobile/src/auth/session_controller.dart';
import 'package:dalijob_mobile/src/auth/token_store.dart';
import 'package:dalijob_mobile/src/features/evaluation/tester_evaluation_screen.dart';
import 'package:dalijob_mobile/src/matching/matching_repository.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

class _MemoryTokenStore implements RefreshTokenStore {
  String? token;

  @override
  Future<void> clear() async => token = null;

  @override
  Future<String?> read() async => token;

  @override
  Future<void> write(String value) async => token = value;
}

void main() {
  testWidgets(
    'tester lab exposes independent candidate, job, and matching sections',
    (tester) async {
      tester.view.physicalSize = const Size(1080, 2280);
      tester.view.devicePixelRatio = 3;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      var candidateReviewSubmitted = false;
      var jobReviewSubmitted = false;
      var preMatchRun = false;
      var detailedMatchRun = false;
      final client = MockClient((request) async {
        if (request.url.path.endsWith('/auth/mobile/sessions')) {
          return _json({
            'access_token': 'access',
            'refresh_token': 'refresh',
            'user': {
              'external_user_id': '42',
              'email': 'tester@example.com',
              'display_name': 'Tester',
              'role': 'admin',
            },
          }, 201);
        }
        if (request.url.path.endsWith('/internal/evaluation/fixture-catalog')) {
          return _json({
            'candidate_fixture_release': 'candidate-fixtures.synthetic.v1',
            'pair_release': 'pairs.v1',
            'benchmark_release': 'jobs.v1',
            'candidates': <Object>[],
            'pairs': <Object>[],
          });
        }
        if (request.url.path.endsWith(
          '/internal/evaluation/candidate-sources',
        )) {
          return _json({
            'candidates': [
              {
                'resume_profile_id': 23,
                'label':
                    '[EVAL synthetic.v1] cand_junior_sparse_01: Junior software candidate with deliberately sparse evidence',
                'fixture_group': 'internal',
                'candidate_profile_id': 'cp_23',
                'profile_created_at': '2026-08-16T00:00:00Z',
              },
            ],
          });
        }
        if (request.url.path.endsWith('/internal/evaluation/job-snapshots')) {
          return _json({
            'snapshots': [
              {
                'public_id': 'ejs_1',
                'review_status': 'accepted',
                'company': 'Example',
                'title': 'Senior Engineer',
              },
            ],
          });
        }
        if (request.url.path.endsWith(
          '/internal/evaluation/candidate-sources/23/profile',
        )) {
          return _json({
            'resume_profile_id': 23,
            'resume_title': 'Resume 23',
            'resume_source': {
              'text': 'Built reliable APIs.',
              'spans': <Object>[],
            },
            'candidate_profile': {
              'candidate_profile_id': 'cp_23',
              'extracted': {
                'skills': ['Python'],
              },
            },
            'annotation_targets': <Object>[],
            'reviews': <Object>[],
          });
        }
        if (request.url.path.endsWith(
          '/internal/evaluation/job-snapshots/ejs_1/profile',
        )) {
          return _json({
            'job_snapshot_id': 'ejs_1',
            'job_title': 'Senior Engineer',
            'job_company': 'Example',
            'job_source': {'text': 'Build reliable APIs.', 'spans': <Object>[]},
            'job_profile': {
              'job_profile_id': 'jp_1',
              'requirements': ['Python'],
            },
            'annotation_targets': <Object>[],
            'reviews': <Object>[],
          });
        }
        if (request.url.path.endsWith(
          '/internal/evaluation/candidate-profiles/cp_23/reviews',
        )) {
          final body = jsonDecode(request.body) as Map<String, dynamic>;
          candidateReviewSubmitted = true;
          expect(body['overall_score'], 50);
          return _json({
            'public_id': 'evp_1',
            'stage': 'candidate_profile',
            'artifact_id': 'cp_23',
            'reviewer_user_id': 1,
            'reviewer_label': 'tester@example.com',
            ...body,
            'created_at': '2026-08-16T00:00:00Z',
          });
        }
        if (request.url.path.endsWith(
          '/internal/evaluation/job-profiles/jp_1/reviews',
        )) {
          final body = jsonDecode(request.body) as Map<String, dynamic>;
          jobReviewSubmitted = true;
          expect(body['overall_score'], 50);
          return _json({
            'public_id': 'evp_2',
            'stage': 'job_profile',
            'artifact_id': 'jp_1',
            'reviewer_user_id': 1,
            'reviewer_label': 'tester@example.com',
            ...body,
            'created_at': '2026-08-16T00:00:00Z',
          });
        }
        if (request.url.path.endsWith('/internal/evaluation/pre-match')) {
          preMatchRun = true;
          return _json({
            'candidate_profile_id': 'cp_23',
            'job_profile_id': 'jp_1',
            'matching_intent': {
              'target_role_text': 'Software Engineer',
              'role_family': 'software_engineering',
              'track': 'individual_contributor',
              'target_level': 'entry',
              'source': 'resume_derived',
            },
            'candidate_target': {
              'career_profile_id': 'career_1',
              'role_family': 'software_engineering',
              'track': 'individual_contributor',
              'level': 'entry',
              'confidence': 0.86,
            },
            'job_target': {
              'primary_role_family': 'software_engineering',
              'track': 'individual_contributor',
              'target_level': 'senior',
            },
            'pre_match': {
              'job_family_pre_match_id': 'jfpm_1',
              'selected_candidate_career_profile_id': 'career_1',
              'family_compatibility': 'exact',
              'track_compatibility': 'exact',
              'level_compatibility': 'multi_level_stretch',
              'proceed_to_detailed_match': true,
              'reason_codes': [
                'INTENT_AND_JOB_FAMILY_EXACT',
                'FAMILY_EXACT',
                'TRACK_EXACT',
                'LEVEL_MULTI_LEVEL_STRETCH',
              ],
              'policy_version': 'job-family-pre-match.v1',
            },
            'cache_status': 'hit',
          });
        }
        if (request.url.path.endsWith('/internal/evaluation/runs')) {
          detailedMatchRun = true;
          return _json({
            'public_id': 'eval_1',
            'job_company': 'Example',
            'job_title': 'Senior Engineer',
            'candidate_profile': {'candidate_profile_id': 'cp_23'},
            'job_profile': {'job_profile_id': 'jp_1'},
            'qualification': {
              'assessment': {'requirement_assessments': <Object>[]},
            },
            'score': {
              'qualification_score': 82,
              'diagnostic_qualification_score': 82,
              'qualification_coverage': 1.0,
              'preference_score': null,
              'preference_coverage': null,
              'preference_state': 'not_configured',
              'overall_score': 82,
              'recommendation': 'good_match',
            },
          });
        }
        throw StateError('Unexpected request ${request.method} ${request.url}');
      });
      final api = ApiClient(
        Uri.parse('https://api.example.com/api/v1/'),
        client,
      );
      final session = SessionController(
        repository: AuthRepository(api),
        tokenStore: _MemoryTokenStore(),
        deviceLabel: 'test device',
      );
      await session.signIn('tester@example.com', 'password123');

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: TesterEvaluationScreen(
              repository: MatchingRepository(api, session),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
      expect(find.byKey(const Key('candidate_profile_lab')), findsOneWidget);
      expect(find.text('Candidate'), findsOneWidget);
      expect(find.text('Job'), findsOneWidget);
      expect(find.text('Pre-match'), findsOneWidget);
      expect(find.text('Detailed'), findsOneWidget);
      expect(find.textContaining('Real ·'), findsOneWidget);

      await tester.tap(
        find.byKey(const Key('load_candidate_profile_evaluation')),
      );
      await tester.pumpAndSettle();
      expect(find.text('Resume source'), findsOneWidget);
      expect(find.text('Candidate Profile'), findsWidgets);
      await tester.drag(
        find.byKey(const Key('tester_evaluation_lab')),
        const Offset(0, -180),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('Candidate Profile').last);
      await tester.pumpAndSettle();
      expect(find.text('Extracted'), findsOneWidget);
      expect(find.text('Overview'), findsOneWidget);
      await tester.drag(
        find.byKey(const Key('tester_evaluation_lab')),
        const Offset(0, -140),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('Extracted'));
      await tester.pumpAndSettle();
      expect(find.text('Skills'), findsOneWidget);
      expect(find.text('Python'), findsOneWidget);
      expect(find.text('View raw data'), findsOneWidget);

      await tester.ensureVisible(find.byType(TextField));
      await tester.enterText(find.byType(TextField), 'Accurate extraction.');
      await tester.pump();
      await tester.ensureVisible(
        find.byKey(const Key('submit_candidate_profile_review')),
      );
      final submit = tester.widget<FilledButton>(
        find.byKey(const Key('submit_candidate_profile_review')),
      );
      expect(submit.onPressed, isNotNull);
      await tester.tap(
        find.byKey(const Key('submit_candidate_profile_review')),
      );
      await tester.pumpAndSettle();
      expect(candidateReviewSubmitted, isTrue);
      expect(
        find.text(
          'Saved. Candidate Profile review was submitted successfully.',
        ),
        findsOneWidget,
      );
      await tester.pump(const Duration(seconds: 5));
      await tester.pumpAndSettle();

      await tester.fling(find.byType(ListView), const Offset(0, 1000), 1000);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Job'));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('job_profile_lab')), findsOneWidget);
      await tester.tap(find.byKey(const Key('load_job_profile_evaluation')));
      await tester.pumpAndSettle();
      expect(find.text('Job description source'), findsOneWidget);
      await tester.ensureVisible(find.text('Job Profile').last);
      await tester.tap(find.text('Job Profile').last);
      await tester.pumpAndSettle();
      expect(find.text('Overview'), findsOneWidget);
      expect(find.text('Requirements'), findsOneWidget);
      await tester.tap(find.text('Requirements'));
      await tester.pumpAndSettle();
      expect(find.text('Python'), findsOneWidget);
      await tester.ensureVisible(find.byType(TextField));
      await tester.enterText(
        find.byType(TextField),
        'Accurate job extraction.',
      );
      await tester.pump();
      await tester.ensureVisible(
        find.byKey(const Key('submit_job_profile_review')),
      );
      await tester.tap(find.byKey(const Key('submit_job_profile_review')));
      await tester.pumpAndSettle();
      expect(jobReviewSubmitted, isTrue);
      expect(
        find.text('Saved. Job Profile review was submitted successfully.'),
        findsOneWidget,
      );

      await tester.pump(const Duration(seconds: 5));
      await tester.pumpAndSettle();
      await tester.fling(find.byType(ListView), const Offset(0, 3000), 2000);
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('Pre-match'));
      await tester.tap(find.text('Pre-match'));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('pre_match_lab')), findsOneWidget);
      await tester.tap(find.byKey(const Key('run_pre_match_evaluation')));
      await tester.pumpAndSettle();
      expect(preMatchRun, isTrue);
      expect(find.text('Proceed to detailed match'), findsOneWidget);
      expect(find.text('Job family'), findsOneWidget);
      expect(find.text('Candidate'), findsNWidgets(2));
      expect(find.text('Job'), findsNWidgets(2));
      expect(find.text('Software engineering'), findsNWidgets(2));
      expect(find.text('Individual contributor'), findsNWidgets(2));
      expect(find.text('Entry'), findsOneWidget);
      expect(find.text('Senior'), findsOneWidget);
      expect(find.text('Multi level stretch'), findsOneWidget);
      expect(find.text('Cache: Hit'), findsOneWidget);

      await tester.fling(find.byType(ListView), const Offset(0, 1000), 1000);
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('Detailed'));
      await tester.tap(find.text('Detailed'));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('matching_lab')), findsOneWidget);
      await tester.tap(find.byKey(const Key('run_matching_evaluation')));
      await tester.pumpAndSettle();
      expect(detailedMatchRun, isTrue);
      expect(find.byKey(const Key('detailed_match_score')), findsOneWidget);
      expect(find.text('82'), findsOneWidget);
      expect(find.text('Match score / 100'), findsOneWidget);
      expect(find.text('Good match'), findsOneWidget);
      expect(find.text('100% qualification coverage'), findsOneWidget);
    },
  );

  testWidgets('tester can load and select a resume in the lab', (tester) async {
    tester.view.physicalSize = const Size(1080, 2280);
    tester.view.devicePixelRatio = 3;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    var resumeLoaded = false;
    var resumeApplied = false;
    final client = MockClient((request) async {
      if (request.url.path.endsWith('/auth/mobile/sessions')) {
        return _json({
          'access_token': 'access',
          'refresh_token': 'refresh',
          'user': {
            'external_user_id': '42',
            'email': 'tester@example.com',
            'display_name': 'Tester',
            'role': 'admin',
          },
        }, 201);
      }
      if (request.url.path.endsWith('/profile/resume-imports')) {
        resumeLoaded = true;
        return _json({
          'file_name': 'new-resume.pdf',
          'document_id': 11,
          'document_version_id': 12,
          'extracted_text_preview': 'Built reliable APIs.',
          'suggestions': {
            'headline': 'Backend engineer',
            'summary': 'Built reliable APIs.',
            'experience': <Object>[],
            'skills': ['Python'],
            'education': <Object>[],
            'certifications': <Object>[],
            'projects': <Object>[],
            'awards': <Object>[],
            'publications': <Object>[],
            'languages': <Object>[],
            'volunteer': <Object>[],
            'target_roles': <Object>[],
            'notes': <Object>[],
          },
          'parse_warning': null,
        });
      }
      if (request.url.path.endsWith('/profile/resume-imports/apply')) {
        resumeApplied = true;
        return _json({
          'id': 24,
          'title': 'new-resume',
          'resume_data': {'summary': 'Built reliable APIs.'},
          'is_default': true,
        });
      }
      if (request.url.path.endsWith('/internal/evaluation/fixture-catalog')) {
        return _json({
          'candidate_fixture_release': 'candidate-fixtures.synthetic.v1',
          'pair_release': 'pairs.v1',
          'benchmark_release': 'jobs.v1',
          'candidates': <Object>[],
          'pairs': <Object>[],
        });
      }
      if (request.url.path.endsWith('/internal/evaluation/candidate-sources')) {
        return _json({
          'candidates': [
            {
              'resume_profile_id': resumeApplied ? 24 : 23,
              'label': resumeApplied ? 'new-resume' : 'Existing resume',
              'fixture_group': 'account',
              'candidate_profile_id': null,
              'profile_created_at': null,
            },
          ],
        });
      }
      if (request.url.path.endsWith('/internal/evaluation/job-snapshots')) {
        return _json({'snapshots': <Object>[]});
      }
      throw StateError('Unexpected request ${request.method} ${request.url}');
    });
    final api = ApiClient(Uri.parse('https://api.example.com/api/v1/'), client);
    final session = SessionController(
      repository: AuthRepository(api),
      tokenStore: _MemoryTokenStore(),
      deviceLabel: 'test device',
    );
    await session.signIn('tester@example.com', 'password123');

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: TesterEvaluationScreen(
            repository: MatchingRepository(api, session),
            pickResume: () async =>
                (name: 'new-resume.pdf', bytes: <int>[37, 80, 68, 70]),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('load_resume_into_tester_lab')));
    await tester.pumpAndSettle();

    expect(resumeLoaded, isTrue);
    expect(resumeApplied, isTrue);
    expect(find.textContaining('new-resume'), findsOneWidget);
    expect(
      find.text('Resume loaded and selected for testing.'),
      findsOneWidget,
    );
    final dropdown = tester.widget<DropdownButtonFormField<int>>(
      find.byKey(const Key('tester_candidate_profile')),
    );
    expect(dropdown.initialValue, 24);
  });
}

http.Response _json(Map<String, dynamic> value, [int status = 200]) =>
    http.Response(
      jsonEncode(value),
      status,
      headers: {'content-type': 'application/json'},
    );
