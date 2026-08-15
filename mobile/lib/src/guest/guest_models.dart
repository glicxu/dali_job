class GuestTrialSnapshot {
  const GuestTrialSnapshot({
    required this.publicId,
    required this.status,
    required this.providerSearchState,
    this.profile,
    this.criteria,
    this.resumeImport,
    this.match,
  });

  final String publicId;
  final String status;
  final String providerSearchState;
  final Map<String, dynamic>? profile;
  final Map<String, dynamic>? criteria;
  final Map<String, dynamic>? resumeImport;
  final Map<String, dynamic>? match;

  bool get isReady => profile?['readiness']?['ready'] == true;
  Map<String, dynamic>? get result => match?['result'] is Map
      ? Map<String, dynamic>.from(match!['result'] as Map)
      : null;

  factory GuestTrialSnapshot.fromJson(Map<String, dynamic> json) =>
      GuestTrialSnapshot(
        publicId: json['public_id'] as String,
        status: json['status'] as String,
        providerSearchState: json['provider_search_state'] as String,
        profile: _map(json['profile']),
        criteria: _map(json['criteria']),
        resumeImport: _map(json['resume_import']),
        match: _map(json['match']),
      );

  GuestTrialSnapshot withMatch(Map<String, dynamic> value) =>
      GuestTrialSnapshot(
        publicId: publicId,
        status: status,
        providerSearchState:
            value['provider_search_state'] as String? ?? providerSearchState,
        profile: profile,
        criteria: criteria,
        resumeImport: resumeImport,
        match: value,
      );

  static Map<String, dynamic>? _map(Object? value) =>
      value is Map ? Map<String, dynamic>.from(value) : null;
}
