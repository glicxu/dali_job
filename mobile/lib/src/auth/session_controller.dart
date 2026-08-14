import 'package:flutter/foundation.dart';

import '../api/api_exception.dart';
import 'auth_models.dart';
import 'auth_repository.dart';
import 'token_store.dart';

enum SessionStatus { bootstrapping, anonymous, authenticated }

class SessionController extends ChangeNotifier {
  SessionController({
    required this.repository,
    required this.tokenStore,
    required this.deviceLabel,
  });

  final AuthRepository repository;
  final RefreshTokenStore tokenStore;
  final String deviceLabel;

  SessionStatus status = SessionStatus.bootstrapping;
  CurrentUser? user;
  String? accessToken;
  Future<void>? _refreshInFlight;

  Future<void> bootstrap() async {
    final savedToken = await tokenStore.read();
    if (savedToken == null) {
      status = SessionStatus.anonymous;
      notifyListeners();
      return;
    }
    try {
      await _accept(await repository.refresh(savedToken));
    } catch (_) {
      await tokenStore.clear();
      status = SessionStatus.anonymous;
      notifyListeners();
    }
  }

  Future<void> signIn(String email, String password) async {
    await _accept(
      await repository.signIn(
        email: email,
        password: password,
        deviceLabel: deviceLabel,
      ),
    );
  }

  Future<String> register(String name, String email, String password) =>
      repository.register(email: email, password: password, displayName: name);

  Future<String> requestPasswordReset(String email) =>
      repository.requestPasswordReset(email);

  Future<T> authorized<T>(Future<T> Function(String token) request) async {
    final token = accessToken;
    if (token == null) throw const ApiException('Please sign in again.');
    try {
      return await request(token);
    } on ApiException catch (error) {
      if (error.statusCode != 401) rethrow;
      await _refreshAccessToken(token);
      return request(accessToken!);
    }
  }

  Future<void> signOut() async {
    final token = accessToken;
    try {
      if (token != null) await repository.signOut(token);
    } finally {
      await tokenStore.clear();
      accessToken = null;
      user = null;
      status = SessionStatus.anonymous;
      notifyListeners();
    }
  }

  Future<void> _accept(MobileTokenPair pair) async {
    await tokenStore.write(pair.refreshToken);
    accessToken = pair.accessToken;
    user = pair.user;
    status = SessionStatus.authenticated;
    notifyListeners();
  }

  Future<void> _refreshAccessToken(String failedToken) async {
    if (accessToken != failedToken) return;
    final currentRefresh = _refreshInFlight;
    if (currentRefresh != null) return currentRefresh;
    final future = _performRefresh();
    _refreshInFlight = future;
    try {
      await future;
    } finally {
      _refreshInFlight = null;
    }
  }

  Future<void> _performRefresh() async {
    final refreshToken = await tokenStore.read();
    if (refreshToken == null) {
      await signOut();
      throw const ApiException('Your session expired. Please sign in again.');
    }
    try {
      await _accept(await repository.refresh(refreshToken));
    } catch (_) {
      await tokenStore.clear();
      accessToken = null;
      user = null;
      status = SessionStatus.anonymous;
      notifyListeners();
      throw const ApiException('Your session expired. Please sign in again.');
    }
  }
}
