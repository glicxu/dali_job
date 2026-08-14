class CurrentUser {
  const CurrentUser({
    required this.id,
    required this.email,
    required this.displayName,
    required this.role,
  });

  final String id;
  final String email;
  final String displayName;
  final String role;

  factory CurrentUser.fromJson(Map<String, dynamic> json) => CurrentUser(
    id: json['external_user_id'] as String,
    email: json['email'] as String,
    displayName: json['display_name'] as String,
    role: json['role'] as String,
  );
}

class MobileTokenPair {
  const MobileTokenPair({
    required this.accessToken,
    required this.refreshToken,
    required this.user,
  });

  final String accessToken;
  final String refreshToken;
  final CurrentUser user;

  factory MobileTokenPair.fromJson(Map<String, dynamic> json) =>
      MobileTokenPair(
        accessToken: json['access_token'] as String,
        refreshToken: json['refresh_token'] as String,
        user: CurrentUser.fromJson(json['user'] as Map<String, dynamic>),
      );
}
