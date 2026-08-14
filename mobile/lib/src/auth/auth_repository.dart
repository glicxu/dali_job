import '../api/api_client.dart';
import 'auth_models.dart';

class AuthRepository {
  AuthRepository(this.api);

  final ApiClient api;

  Future<MobileTokenPair> signIn({
    required String email,
    required String password,
    required String deviceLabel,
  }) async => MobileTokenPair.fromJson(
    await api.post(
      'auth/mobile/sessions',
      body: {
        'email': email.trim(),
        'password': password,
        'device_label': deviceLabel,
      },
    ),
  );

  Future<MobileTokenPair> refresh(String refreshToken) async =>
      MobileTokenPair.fromJson(
        await api.post(
          'auth/mobile/sessions/refresh',
          body: {'refresh_token': refreshToken},
        ),
      );

  Future<String> register({
    required String email,
    required String password,
    required String displayName,
  }) async {
    final json = await api.post(
      'auth/register',
      body: {
        'email': email.trim(),
        'password': password,
        'display_name': displayName.trim(),
        // The profile screen will collect an IANA zone; UTC is always valid.
        'timezone': 'UTC',
      },
    );
    return json['message'] as String;
  }

  Future<String> requestPasswordReset(String email) async {
    final json = await api.post(
      'auth/forgot-password',
      body: {'email': email.trim()},
    );
    return json['message'] as String;
  }

  Future<void> signOut(String accessToken) =>
      api.delete('auth/mobile/sessions/current', accessToken: accessToken);
}
