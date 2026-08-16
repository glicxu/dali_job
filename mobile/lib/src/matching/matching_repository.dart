import '../api/api_client.dart';
import '../auth/session_controller.dart';
import 'matching_models.dart';

class MatchingRepository {
  MatchingRepository(this.api, this.session);

  final ApiClient api;
  final SessionController session;

  Future<OnboardingSnapshot> loadOnboarding() async {
    final profiles = await listResumeProfiles();
    final criteria = await listCriteria();
    final schedules = await listSchedules();
    final entitlement = await getEntitlement();
    return OnboardingSnapshot(
      profiles: profiles,
      criteria: criteria,
      schedules: schedules,
      entitlement: entitlement,
    );
  }

  Future<List<ResumeProfile>> listResumeProfiles() => session.authorized((
    token,
  ) async {
    final json = await api.get('resume-profiles', accessToken: token);
    return (json['resume_profiles'] as List)
        .map(
          (item) =>
              ResumeProfile.fromJson(Map<String, dynamic>.from(item as Map)),
        )
        .toList();
  });

  Future<CandidateProfileV2?> getCandidateProfile(int resumeProfileId) =>
      session.authorized((token) async {
        final json = await api.getNullable(
          'resumes/$resumeProfileId/candidate-profile',
          accessToken: token,
        );
        return json == null ? null : CandidateProfileV2.fromJson(json);
      });

  Future<CandidateProfileV2> confirmCareerProfile({
    required CandidateProfileV2 profile,
    required String careerProfileId,
  }) => session.authorized(
    (token) async => CandidateProfileV2.fromJson(
      await api.put(
        'candidate-profiles/${profile.id}/primary-career-profile',
        accessToken: token,
        body: {
          'expected_revision': profile.selectionRevision,
          'primary_career_profile_id': careerProfileId,
        },
      ),
    ),
  );

  Future<PreferenceRevision?> getPreferences() =>
      session.authorized((token) async {
        final json = await api.getNullable(
          'users/me/matching-preferences',
          accessToken: token,
        );
        return json == null ? null : PreferenceRevision.fromJson(json);
      });

  Future<PreferenceRevision> putPreferences({
    required int expectedRevision,
    required Map<String, dynamic> preferences,
  }) => session.authorized(
    (token) async => PreferenceRevision.fromJson(
      await api.put(
        'users/me/matching-preferences',
        accessToken: token,
        body: {
          'expected_revision': expectedRevision,
          'preferences': preferences,
        },
      ),
    ),
  );

  Future<EligibilityRevision?> getEligibility() =>
      session.authorized((token) async {
        final json = await api.getNullable(
          'users/me/eligibility-facts',
          accessToken: token,
        );
        return json == null ? null : EligibilityRevision.fromJson(json);
      });

  Future<EligibilityRevision> putEligibility({
    required int expectedRevision,
    required Map<String, dynamic> facts,
  }) => session.authorized(
    (token) async => EligibilityRevision.fromJson(
      await api.put(
        'users/me/eligibility-facts',
        accessToken: token,
        body: {'expected_revision': expectedRevision, 'facts': facts},
      ),
    ),
  );

  Future<ResumeProfile> createResumeProfile({
    required String title,
    required String headline,
    required String summary,
    required List<String> skills,
    required List<String> targetRoles,
  }) => session.authorized(
    (token) async => ResumeProfile.fromJson(
      await api.post(
        'resume-profiles',
        accessToken: token,
        body: {
          'title': title,
          'is_default': true,
          'resume_data': _resumeData(
            headline: headline,
            summary: summary,
            skills: skills,
            targetRoles: targetRoles,
          ),
        },
      ),
    ),
  );

  Future<ResumeProfile> uploadAndApplyResume({
    required String fileName,
    required List<int> bytes,
    String? profileTitle,
  }) => session.authorized((token) async {
    final imported = await api.postFile(
      'profile/resume-imports',
      fieldName: 'file',
      fileName: fileName,
      bytes: bytes,
      contentType: fileName.toLowerCase().endsWith('.pdf')
          ? 'application/pdf'
          : 'text/plain',
      accessToken: token,
    );
    var applied = await api.post(
      'profile/resume-imports/apply',
      accessToken: token,
      body: {
        'resume_data': imported['suggestions'],
        'source_document_id': imported['document_id'],
        'source_document_version_id': imported['document_version_id'],
      },
    );
    if (profileTitle != null) {
      applied = await api.patch(
        'resume-profiles/${applied['id']}',
        accessToken: token,
        body: {'title': profileTitle, 'is_default': true},
      );
    }
    return ResumeProfile.fromJson(applied);
  });

  Future<List<SearchCriterion>> listCriteria() => session.authorized((
    token,
  ) async {
    final json = await api.get('job-search/criteria', accessToken: token);
    return (json['criteria'] as List)
        .map(
          (item) =>
              SearchCriterion.fromJson(Map<String, dynamic>.from(item as Map)),
        )
        .toList();
  });

  Future<SearchCriterion> createCriterion({
    required int resumeProfileId,
    required String keyword,
    required String location,
  }) => session.authorized(
    (token) async => SearchCriterion.fromJson(
      await api.post(
        'job-search/criteria',
        accessToken: token,
        body: {
          'resume_profile_id': resumeProfileId,
          'keyword': keyword,
          'location': location,
        },
      ),
    ),
  );

  Future<Entitlement> getEntitlement() => session.authorized(
    (token) async => Entitlement.fromJson(
      await api.get('account/entitlements', accessToken: token),
    ),
  );

  Future<List<SearchSchedule>> listSchedules() => session.authorized((
    token,
  ) async {
    final json = await api.get('automation/schedules', accessToken: token);
    return (json['schedules'] as List)
        .map(
          (item) =>
              SearchSchedule.fromJson(Map<String, dynamic>.from(item as Map)),
        )
        .toList();
  });

  Future<SearchSchedule> createSchedule({
    required SearchCriterion criterion,
    required ResumeProfile profile,
    required Entitlement entitlement,
  }) => session.authorized(
    (token) async => SearchSchedule.fromJson(
      await api.post(
        'automation/schedules',
        accessToken: token,
        body: {
          'criterion_id': criterion.id,
          'resume_profile_id': profile.id,
          'interval_minutes': entitlement.minimumIntervalMinutes,
          'enabled': true,
        },
      ),
    ),
  );

  Future<SearchSchedule> setScheduleEnabled(
    SearchSchedule schedule,
    bool enabled,
  ) => session.authorized(
    (token) async => SearchSchedule.fromJson(
      await api.post(
        'automation/schedules/${schedule.id}/${enabled ? 'resume' : 'pause'}',
        accessToken: token,
      ),
    ),
  );

  Future<Map<String, dynamic>> runScheduleNow(SearchSchedule schedule) =>
      session.authorized((token) {
        return api.post(
          'automation/schedules/${schedule.id}/run-now',
          accessToken: token,
        );
      });

  Future<Map<String, dynamic>> rerunMatchSchedule(int scheduleId) =>
      session.authorized((token) {
        return api.post(
          'automation/schedules/$scheduleId/run-now',
          accessToken: token,
        );
      });

  Future<List<MatchInboxItem>> listMatches() => session.authorized((
    token,
  ) async {
    final json = await api.get('match-inbox', accessToken: token);
    return (json['items'] as List)
        .map(
          (item) =>
              MatchInboxItem.fromJson(Map<String, dynamic>.from(item as Map)),
        )
        .toList();
  });

  Future<MatchInboxItem> markMatchRead(int matchId) => session.authorized(
    (token) async => MatchInboxItem.fromJson(
      await api.post('match-inbox/$matchId/read', accessToken: token),
    ),
  );

  Future<MatchFeedback> putMatchFeedback({
    required int matchId,
    required int score,
    required String rationale,
  }) => session.authorized(
    (token) async => MatchFeedback.fromJson(
      await api.put(
        'match-inbox/$matchId/feedback',
        accessToken: token,
        body: {'score': score, 'rationale': rationale},
      ),
    ),
  );

  Future<TesterFixtures> loadTesterFixtures() =>
      session.authorized((token) async {
        final catalog = await api.get(
          'internal/evaluation/fixture-catalog',
          accessToken: token,
        );
        final snapshots = await api.get(
          'internal/evaluation/job-snapshots',
          accessToken: token,
        );
        return TesterFixtures(
          catalog: catalog,
          jobs: (snapshots['snapshots'] as List)
              .map((item) => Map<String, dynamic>.from(item as Map))
              .toList(),
        );
      });

  Future<Map<String, dynamic>> startTesterEvaluation({
    required int resumeProfileId,
    required String jobSnapshotId,
    required String candidateFixtureRelease,
  }) => session.authorized(
    (token) => api.post(
      'internal/evaluation/runs',
      accessToken: token,
      body: {
        'resume_profile_id': resumeProfileId,
        'job_snapshot_id': jobSnapshotId,
        'candidate_fixture_release': candidateFixtureRelease,
      },
    ),
  );

  Future<Map<String, dynamic>> submitTesterReview({
    required String runId,
    required int score,
    required String rationale,
  }) => session.authorized(
    (token) => api.post(
      'internal/evaluation/runs/$runId/match-reviews',
      accessToken: token,
      body: {
        'review_kind': 'independent',
        'overall_score': score,
        'confidence': 1.0,
        'rationale': rationale.trim(),
      },
    ),
  );

  Map<String, dynamic> _resumeData({
    required String headline,
    required String summary,
    required List<String> skills,
    required List<String> targetRoles,
  }) => {
    'headline': headline,
    'summary': summary,
    'experience': <String>[],
    'skills': skills,
    'education': <String>[],
    'certifications': <String>[],
    'projects': <String>[],
    'awards': <String>[],
    'publications': <String>[],
    'languages': <String>[],
    'volunteer': <String>[],
    'target_roles': targetRoles,
    'notes': <String>[],
  };
}

class TesterFixtures {
  const TesterFixtures({required this.catalog, required this.jobs});

  final Map<String, dynamic> catalog;
  final List<Map<String, dynamic>> jobs;
}
