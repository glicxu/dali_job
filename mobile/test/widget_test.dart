import 'dart:convert';

import 'package:dalijob_mobile/src/api/api_client.dart';
import 'package:dalijob_mobile/src/app.dart';
import 'package:dalijob_mobile/src/auth/auth_repository.dart';
import 'package:dalijob_mobile/src/auth/session_controller.dart';
import 'package:dalijob_mobile/src/auth/token_store.dart';
import 'package:dalijob_mobile/src/config/app_environment.dart';
import 'package:dalijob_mobile/src/guest/guest_controller.dart';
import 'package:dalijob_mobile/src/guest/guest_repository.dart';
import 'package:flutter/material.dart' show ChoiceChip;
import 'package:flutter/widgets.dart' show Key, ListView;
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

class _MemoryGuestStore implements GuestCredentialStore {
  String? credential;

  @override
  Future<void> clear() async => credential = null;

  @override
  Future<String?> read() async => credential;

  @override
  Future<void> write(String value) async => credential = value;
}

void main() {
  testWidgets('shows sign in after anonymous bootstrap', (tester) async {
    final api = ApiClient(
      Uri.parse('https://api.example.com/api/v1/'),
      MockClient((_) async => throw UnimplementedError()),
    );
    final controller = SessionController(
      repository: AuthRepository(api),
      tokenStore: _MemoryTokenStore(),
      deviceLabel: 'test device',
    );
    final guest = GuestController(
      repository: GuestRepository(api),
      credentialStore: _MemoryGuestStore(),
    );
    await controller.bootstrap();
    await guest.bootstrap();

    await tester.pumpWidget(
      DaliJobApp(
        environment: AppEnvironment(
          name: 'test',
          apiBaseUrl: Uri.parse('https://api.example.com/api/v1/'),
        ),
        session: controller,
        guest: guest,
      ),
    );

    expect(find.text('DaliJob'), findsOneWidget);
    expect(find.text('Sign in'), findsOneWidget);
    expect(find.text('New to DaliJob? Create account'), findsOneWidget);
    expect(find.text('Try a match without an account'), findsOneWidget);
  });

  testWidgets('starts an account-free trial and shows profile readiness intake', (
    tester,
  ) async {
    final api = ApiClient(
      Uri.parse('https://api.example.com/api/v1/'),
      MockClient((request) async {
        if (request.method == 'POST' &&
            request.url.path.endsWith('/guest-trials')) {
          return http.Response(
            '{"public_id":"trial","guest_secret":"secret","guest_credential":"trial.secret","status":"active","expires_at":"2026-08-15T00:00:00Z"}',
            201,
          );
        }
        if (request.url.path.endsWith('/current/match')) {
          return http.Response(
            '{"operation_id":null,"status":"not_started","provider_search_state":"available","retryable":false}',
            200,
          );
        }
        if (request.url.path.endsWith('/guest-trials/current')) {
          expect(request.headers['Authorization'], 'Guest trial.secret');
          return http.Response(
            '{"public_id":"trial","status":"active","provider_search_state":"available","profile":null,"criteria":null,"resume_import":null}',
            200,
          );
        }
        throw StateError('Unexpected request ${request.method} ${request.url}');
      }),
    );
    final session = SessionController(
      repository: AuthRepository(api),
      tokenStore: _MemoryTokenStore(),
      deviceLabel: 'test device',
    );
    final store = _MemoryGuestStore();
    final guest = GuestController(
      repository: GuestRepository(api),
      credentialStore: store,
    );
    await session.bootstrap();
    await guest.bootstrap();
    await tester.pumpWidget(
      DaliJobApp(
        environment: AppEnvironment(
          name: 'test',
          apiBaseUrl: Uri.parse('https://api.example.com/api/v1/'),
        ),
        session: session,
        guest: guest,
      ),
    );

    await tester.tap(find.text('Try a match without an account'));
    await tester.pumpAndSettle();

    expect(store.credential, 'trial.secret');
    expect(find.text('Add your resume'), findsOneWidget);
    expect(find.text('Upload your resume'), findsOneWidget);
    expect(find.text("Don't have a resume?"), findsOneWidget);
    expect(find.byKey(const Key('guest_profile_text')), findsNothing);

    await tester.tap(find.text("Don't have a resume?"));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('guest_profile_text')), findsOneWidget);
    expect(find.text('Use this profile'), findsOneWidget);
    expect(find.text('Professional headline'), findsNothing);
    expect(find.text('Skills'), findsNothing);
  });

  testWidgets('offers target roles inferred from the ready profile', (
    tester,
  ) async {
    final api = ApiClient(
      Uri.parse('https://api.example.com/api/v1/'),
      MockClient((request) async {
        if (request.url.path.endsWith('/current/match')) {
          return http.Response(
            '{"operation_id":null,"status":"not_started","provider_search_state":"available"}',
            200,
          );
        }
        return http.Response(
          jsonEncode({
            'public_id': 'trial',
            'status': 'active',
            'provider_search_state': 'available',
            'profile': {
              'resume_data': {
                'target_roles': ['Backend Engineer', 'Platform Engineer'],
              },
              'readiness': {'ready': true},
            },
            'criteria': null,
            'resume_import': null,
          }),
          200,
        );
      }),
    );
    final session = SessionController(
      repository: AuthRepository(api),
      tokenStore: _MemoryTokenStore(),
      deviceLabel: 'test device',
    );
    final store = _MemoryGuestStore()..credential = 'trial.secret';
    final guest = GuestController(
      repository: GuestRepository(api),
      credentialStore: store,
    );
    await session.bootstrap();
    await guest.bootstrap();
    await tester.pumpWidget(
      DaliJobApp(
        environment: AppEnvironment(
          name: 'test',
          apiBaseUrl: Uri.parse('https://api.example.com/api/v1/'),
        ),
        session: session,
        guest: guest,
      ),
    );

    expect(find.text('Suggested roles'), findsOneWidget);
    expect(find.text('Backend Engineer'), findsOneWidget);
    expect(find.text('Platform Engineer'), findsOneWidget);

    await tester.tap(find.text('Backend Engineer'));
    await tester.pump();

    final selected = tester.widget<ChoiceChip>(
      find.widgetWithText(ChoiceChip, 'Backend Engineer'),
    );
    expect(selected.selected, isTrue);
  });

  testWidgets(
    'shows fetched job description in-app and offers account creation',
    (tester) async {
      final api = ApiClient(
        Uri.parse('https://api.example.com/api/v1/'),
        MockClient((request) async {
          if (request.url.path.endsWith('/current/match')) {
            return http.Response(
              jsonEncode({
                'operation_id': 7,
                'status': 'result_ready',
                'provider_search_state': 'consumed',
                'result': {
                  'title': 'Backend Engineer',
                  'company': 'Example',
                  'location': 'Remote',
                  'source_url': 'https://jobs.example/backend',
                  'match_score': 9,
                  'summary': 'Strong Python match.',
                  'job_description':
                      'Build reliable Python services and production APIs.',
                },
              }),
              200,
            );
          }
          return http.Response(
            jsonEncode({
              'public_id': 'trial',
              'status': 'active',
              'provider_search_state': 'consumed',
              'profile': {
                'resume_data': {
                  'target_roles': ['Backend Engineer'],
                },
                'readiness': {'ready': true},
              },
              'criteria': {'keyword': 'Backend Engineer', 'location': 'Remote'},
              'resume_import': null,
            }),
            200,
          );
        }),
      );
      final session = SessionController(
        repository: AuthRepository(api),
        tokenStore: _MemoryTokenStore(),
        deviceLabel: 'test device',
      );
      final store = _MemoryGuestStore()..credential = 'trial.secret';
      final guest = GuestController(
        repository: GuestRepository(api),
        credentialStore: store,
      );
      await session.bootstrap();
      await guest.bootstrap();
      await tester.pumpWidget(
        DaliJobApp(
          environment: AppEnvironment(
            name: 'test',
            apiBaseUrl: Uri.parse('https://api.example.com/api/v1/'),
          ),
          session: session,
          guest: guest,
        ),
      );

      expect(find.text('View original job'), findsNothing);
      expect(find.text('View job description'), findsOneWidget);
      expect(find.text('Get new matches automatically'), findsOneWidget);
      expect(find.text('Create an account'), findsOneWidget);

      await tester.tap(find.text('View job description'));
      await tester.pumpAndSettle();
      expect(
        find.text('Build reliable Python services and production APIs.'),
        findsOneWidget,
      );

      await tester.tap(find.text('View job description'));
      await tester.pumpAndSettle();
      await tester.scrollUntilVisible(find.text('Create an account'), 300);
      await tester.drag(find.byType(ListView), const Offset(0, -100));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Create an account'));
      await tester.pumpAndSettle();

      expect(find.text('Create your job matching account'), findsOneWidget);
      expect(find.text('Try a match without an account'), findsNothing);
    },
  );
}
