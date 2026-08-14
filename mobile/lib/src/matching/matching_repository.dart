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
