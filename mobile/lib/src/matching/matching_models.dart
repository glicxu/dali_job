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
  });

  final int matchId;
  final String title;
  final String company;
  final int matchScore;
  final String status;
  final Map<String, dynamic> matchData;
  final Map<String, dynamic> resumeData;
  final Map<String, dynamic> jobData;
  final DateTime createdAt;
  final String? sourceUrl;
  final MatchFeedback? userFeedback;

  bool get isRead => status == 'read';

  factory MatchInboxItem.fromJson(Map<String, dynamic> json) => MatchInboxItem(
    matchId: json['match_id'] as int,
    title: json['title'] as String,
    company: json['company'] as String,
    matchScore: json['match_score'] as int,
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
  );
}

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
