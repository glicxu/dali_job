class ResumeProfile {
  const ResumeProfile({
    required this.id,
    required this.title,
    required this.resumeData,
    required this.isDefault,
  });

  final int id;
  final String title;
  final Map<String, dynamic> resumeData;
  final bool isDefault;

  factory ResumeProfile.fromJson(Map<String, dynamic> json) => ResumeProfile(
    id: json['id'] as int,
    title: json['title'] as String,
    resumeData: Map<String, dynamic>.from(json['resume_data'] as Map),
    isDefault: json['is_default'] as bool,
  );
}

class SearchCriterion {
  const SearchCriterion({
    required this.id,
    required this.keyword,
    required this.location,
    required this.resumeProfileId,
  });

  final int id;
  final String keyword;
  final String? location;
  final int? resumeProfileId;

  factory SearchCriterion.fromJson(Map<String, dynamic> json) =>
      SearchCriterion(
        id: json['id'] as int,
        keyword: json['keyword'] as String,
        location: json['location'] as String?,
        resumeProfileId: json['resume_profile_id'] as int?,
      );
}

class CandidateCareerProfile {
  const CandidateCareerProfile({
    required this.id,
    required this.roleFamily,
    required this.track,
    required this.level,
    required this.confidence,
  });

  final String id;
  final String roleFamily;
  final String track;
  final String level;
  final double confidence;

  factory CandidateCareerProfile.fromJson(Map<String, dynamic> json) =>
      CandidateCareerProfile(
        id: json['career_profile_id'] as String,
        roleFamily: json['role_family'] as String,
        track: json['track'] as String,
        level: json['level'] as String,
        confidence: (json['confidence'] as num).toDouble(),
      );
}

class CandidateProfileV2 {
  const CandidateProfileV2({
    required this.id,
    required this.resumeProfileId,
    required this.careerProfiles,
    required this.selectionRevision,
    required this.primaryCareerProfileId,
  });

  final String id;
  final int? resumeProfileId;
  final List<CandidateCareerProfile> careerProfiles;
  final int selectionRevision;
  final String? primaryCareerProfileId;

  factory CandidateProfileV2.fromJson(Map<String, dynamic> json) {
    final selection = Map<String, dynamic>.from(json['selection'] as Map);
    return CandidateProfileV2(
      id: json['candidate_profile_id'] as String,
      resumeProfileId: json['resume_profile_id'] as int?,
      careerProfiles: _mapList(
        json['career_profiles'],
      ).map(CandidateCareerProfile.fromJson).toList(),
      selectionRevision: selection['revision'] as int,
      primaryCareerProfileId: selection['primary_career_profile_id'] as String?,
    );
  }
}

class PreferenceRevision {
  const PreferenceRevision({required this.revision, required this.preferences});
  final int revision;
  final Map<String, dynamic> preferences;

  factory PreferenceRevision.fromJson(Map<String, dynamic> json) =>
      PreferenceRevision(
        revision: json['revision'] as int,
        preferences: Map<String, dynamic>.from(json['preferences'] as Map),
      );
}

class EligibilityRevision {
  const EligibilityRevision({required this.revision, required this.facts});
  final int revision;
  final Map<String, dynamic> facts;

  factory EligibilityRevision.fromJson(Map<String, dynamic> json) =>
      EligibilityRevision(
        revision: json['revision'] as int,
        facts: Map<String, dynamic>.from(json['facts'] as Map),
      );
}

class Entitlement {
  const Entitlement({
    required this.tierCode,
    required this.searchesPerPeriod,
    required this.searchesAvailable,
    required this.minimumIntervalMinutes,
    required this.periodEndsAt,
  });

  final String tierCode;
  final int? searchesPerPeriod;
  final int? searchesAvailable;
  final int minimumIntervalMinutes;
  final DateTime periodEndsAt;

  factory Entitlement.fromJson(Map<String, dynamic> json) => Entitlement(
    tierCode: json['tier_code'] as String,
    searchesPerPeriod: json['searches_per_period'] as int?,
    searchesAvailable: json['searches_available'] as int?,
    minimumIntervalMinutes: json['minimum_interval_minutes'] as int,
    periodEndsAt: DateTime.parse(json['period_ends_at'] as String),
  );
}

class SearchSchedule {
  const SearchSchedule({
    required this.id,
    required this.criterionId,
    required this.resumeProfileId,
    required this.enabled,
    required this.nextRunAt,
    required this.failureCount,
    this.pausedReason,
  });

  final int id;
  final int criterionId;
  final int resumeProfileId;
  final bool enabled;
  final DateTime nextRunAt;
  final int failureCount;
  final String? pausedReason;

  factory SearchSchedule.fromJson(Map<String, dynamic> json) => SearchSchedule(
    id: json['id'] as int,
    criterionId: json['criterion_id'] as int,
    resumeProfileId: json['resume_profile_id'] as int,
    enabled: json['enabled'] as bool,
    nextRunAt: DateTime.parse(json['next_run_at'] as String),
    failureCount: json['consecutive_failure_count'] as int,
    pausedReason: json['paused_reason'] as String?,
  );
}

class MatchInboxItem {
  const MatchInboxItem({
    required this.matchId,
    required this.searchScheduleId,
    required this.title,
    required this.company,
    required this.matchScore,
    required this.status,
    required this.matchData,
    required this.resumeData,
    required this.jobData,
    required this.createdAt,
    this.sourceUrl,
    this.userFeedback,
    this.v2Result,
  });

  final int matchId;
  final int searchScheduleId;
  final String title;
  final String company;
  final int? matchScore;
  final String status;
  final Map<String, dynamic> matchData;
  final Map<String, dynamic> resumeData;
  final Map<String, dynamic> jobData;
  final DateTime createdAt;
  final String? sourceUrl;
  final MatchFeedback? userFeedback;
  final V2MatchResult? v2Result;

  int? get overallScore => v2Result?.scores.overallScore;
  bool get needsMoreInformation =>
      v2Result?.scores.recommendation == 'needs_more_information';

  bool get isRead => status == 'read';

  factory MatchInboxItem.fromJson(Map<String, dynamic> json) => MatchInboxItem(
    matchId: json['match_id'] as int,
    searchScheduleId: json['search_schedule_id'] as int,
    title: json['title'] as String,
    company: json['company'] as String,
    matchScore: json['match_score'] as int?,
    status: json['status'] as String,
    matchData: Map<String, dynamic>.from(json['match_data'] as Map),
    resumeData: Map<String, dynamic>.from(
      json['resume_data'] as Map? ?? const {},
    ),
    jobData: Map<String, dynamic>.from(json['job_data'] as Map? ?? const {}),
    createdAt: DateTime.parse(json['created_at'] as String),
    sourceUrl: json['source_url'] as String?,
    userFeedback: json['user_feedback'] is Map
        ? MatchFeedback.fromJson(
            Map<String, dynamic>.from(json['user_feedback'] as Map),
          )
        : null,
    v2Result: json['matching_v2_result'] is Map
        ? V2MatchResult.fromJson(
            Map<String, dynamic>.from(json['matching_v2_result'] as Map),
          )
        : _embeddedV2Result(json),
  );
}

V2MatchResult? _embeddedV2Result(Map<String, dynamic> json) {
  final matchData = json['match_data'];
  if (matchData is! Map || matchData['pipeline'] != 'matching_v2') return null;
  final score = matchData['score'];
  final explanation = matchData['explanation'];
  final matchId = matchData['matching_v2_result_id'];
  if (score is! Map || explanation is! Map || matchId is! String) return null;
  return V2MatchResult.fromJson({
    'match_id': matchId,
    'qualification_assessment_id':
        matchData['qualification_assessment_id']?.toString() ?? '',
    'scores': score,
    'explanation': explanation,
    'policy': const <String, dynamic>{},
    'legacy_score': json['match_score'],
    'created_at': json['created_at'],
  });
}

class V2MatchResult {
  const V2MatchResult({
    required this.matchId,
    required this.qualificationAssessmentId,
    required this.scores,
    required this.explanation,
    required this.policy,
    required this.createdAt,
    this.legacyScore,
  });

  final String matchId;
  final String qualificationAssessmentId;
  final V2MatchScores scores;
  final V2MatchExplanation explanation;
  final Map<String, dynamic> policy;
  final int? legacyScore;
  final DateTime createdAt;

  factory V2MatchResult.fromJson(Map<String, dynamic> json) => V2MatchResult(
    matchId: json['match_id'] as String,
    qualificationAssessmentId:
        json['qualification_assessment_id'] as String? ?? '',
    scores: V2MatchScores.fromJson(
      Map<String, dynamic>.from(json['scores'] as Map),
    ),
    explanation: V2MatchExplanation.fromJson(
      Map<String, dynamic>.from(json['explanation'] as Map),
    ),
    policy: Map<String, dynamic>.from(json['policy'] as Map? ?? const {}),
    legacyScore: json['legacy_score'] as int?,
    createdAt: DateTime.parse(json['created_at'] as String),
  );
}

class V2MatchScores {
  const V2MatchScores({
    required this.qualificationScore,
    required this.qualificationCoverage,
    required this.preferenceScore,
    required this.preferenceCoverage,
    required this.overallScore,
    required this.recommendation,
    required this.reasonCodes,
    required this.questions,
    required this.gates,
  });

  final int? qualificationScore;
  final double qualificationCoverage;
  final int? preferenceScore;
  final double? preferenceCoverage;
  final int? overallScore;
  final String recommendation;
  final List<String> reasonCodes;
  final List<String> questions;
  final List<V2GateResult> gates;

  factory V2MatchScores.fromJson(Map<String, dynamic> json) => V2MatchScores(
    qualificationScore: json['qualification_score'] as int?,
    qualificationCoverage:
        (json['qualification_coverage'] as num?)?.toDouble() ?? 0,
    preferenceScore: json['preference_score'] as int?,
    preferenceCoverage: (json['preference_coverage'] as num?)?.toDouble(),
    overallScore: json['overall_score'] as int?,
    recommendation:
        json['recommendation'] as String? ?? 'needs_more_information',
    reasonCodes: _stringList(json['reason_codes']),
    questions: _stringList(json['questions']),
    gates: _mapList(json['gates']).map(V2GateResult.fromJson).toList(),
  );
}

class V2GateResult {
  const V2GateResult({
    required this.constraintKey,
    required this.owner,
    required this.status,
    required this.reasonCode,
  });

  final String constraintKey;
  final String owner;
  final String status;
  final String reasonCode;

  factory V2GateResult.fromJson(Map<String, dynamic> json) => V2GateResult(
    constraintKey: json['constraint_key'] as String? ?? '',
    owner: json['owner'] as String? ?? '',
    status: json['status'] as String? ?? 'unknown',
    reasonCode: json['reason_code'] as String? ?? '',
  );
}

class V2ExplanationItem {
  const V2ExplanationItem({
    required this.key,
    required this.label,
    required this.detail,
    required this.evidenceRefs,
  });

  final String key;
  final String label;
  final String detail;
  final List<String> evidenceRefs;

  factory V2ExplanationItem.fromJson(Map<String, dynamic> json) =>
      V2ExplanationItem(
        key: json['key'] as String? ?? '',
        label: json['label'] as String? ?? '',
        detail: json['detail'] as String? ?? '',
        evidenceRefs: _stringList(json['evidence_refs']),
      );
}

class V2MatchExplanation {
  const V2MatchExplanation({
    required this.summary,
    required this.strengths,
    required this.gaps,
    required this.unknowns,
    required this.preferenceConflicts,
    required this.questions,
  });

  final String summary;
  final List<V2ExplanationItem> strengths;
  final List<V2ExplanationItem> gaps;
  final List<V2ExplanationItem> unknowns;
  final List<V2ExplanationItem> preferenceConflicts;
  final List<String> questions;

  factory V2MatchExplanation.fromJson(Map<String, dynamic> json) =>
      V2MatchExplanation(
        summary: json['summary'] as String? ?? '',
        strengths: _explanationItems(json['strengths']),
        gaps: _explanationItems(json['gaps']),
        unknowns: _explanationItems(json['unknowns']),
        preferenceConflicts: _explanationItems(json['preference_conflicts']),
        questions: _stringList(json['questions']),
      );
}

List<String> _stringList(Object? value) =>
    value is List ? value.map((item) => item.toString()).toList() : const [];

List<Map<String, dynamic>> _mapList(Object? value) => value is List
    ? value
          .whereType<Map>()
          .map((item) => Map<String, dynamic>.from(item))
          .toList()
    : const [];

List<V2ExplanationItem> _explanationItems(Object? value) =>
    _mapList(value).map(V2ExplanationItem.fromJson).toList();

class MatchFeedback {
  const MatchFeedback({
    required this.score,
    required this.recommendation,
    required this.rationale,
    required this.createdAt,
    required this.updatedAt,
  });

  final int score;
  final String recommendation;
  final String rationale;
  final DateTime createdAt;
  final DateTime updatedAt;

  factory MatchFeedback.fromJson(Map<String, dynamic> json) => MatchFeedback(
    score: json['score'] as int,
    recommendation: json['recommendation'] as String,
    rationale: json['rationale'] as String? ?? '',
    createdAt: DateTime.parse(json['created_at'] as String),
    updatedAt: DateTime.parse(json['updated_at'] as String),
  );
}

class OnboardingSnapshot {
  const OnboardingSnapshot({
    required this.profiles,
    required this.criteria,
    required this.schedules,
    required this.entitlement,
  });

  final List<ResumeProfile> profiles;
  final List<SearchCriterion> criteria;
  final List<SearchSchedule> schedules;
  final Entitlement entitlement;
}
