import 'package:dalijob_mobile/src/api/api_client.dart';
import 'package:dalijob_mobile/src/app.dart';
import 'package:dalijob_mobile/src/auth/auth_repository.dart';
import 'package:dalijob_mobile/src/auth/session_controller.dart';
import 'package:dalijob_mobile/src/auth/token_store.dart';
import 'package:dalijob_mobile/src/config/app_environment.dart';
import 'package:flutter_test/flutter_test.dart';
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
  testWidgets('shows sign in after anonymous bootstrap', (tester) async {
    final controller = SessionController(
      repository: AuthRepository(
        ApiClient(
          Uri.parse('https://api.example.com/api/v1/'),
          MockClient((_) async => throw UnimplementedError()),
        ),
      ),
      tokenStore: _MemoryTokenStore(),
      deviceLabel: 'test device',
    );
    await controller.bootstrap();

    await tester.pumpWidget(
      DaliJobApp(
        environment: AppEnvironment(
          name: 'test',
          apiBaseUrl: Uri.parse('https://api.example.com/api/v1/'),
        ),
        session: controller,
      ),
    );

    expect(find.text('DaliJob'), findsOneWidget);
    expect(find.text('Sign in'), findsOneWidget);
    expect(find.text('New to DaliJob? Create account'), findsOneWidget);
  });
}
