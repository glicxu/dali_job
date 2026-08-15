import 'package:flutter_secure_storage/flutter_secure_storage.dart';

abstract interface class RefreshTokenStore {
  Future<String?> read();
  Future<void> write(String token);
  Future<void> clear();
}

class FlutterSecureTokenStore implements RefreshTokenStore {
  const FlutterSecureTokenStore(this.storage);

  static const _key = 'dalijob_mobile_refresh_token';
  final FlutterSecureStorage storage;

  @override
  Future<String?> read() => storage.read(key: _key);

  @override
  Future<void> write(String token) => storage.write(key: _key, value: token);

  @override
  Future<void> clear() => storage.delete(key: _key);
}

abstract interface class GuestCredentialStore {
  Future<String?> read();
  Future<void> write(String credential);
  Future<void> clear();
}

class FlutterSecureGuestCredentialStore implements GuestCredentialStore {
  const FlutterSecureGuestCredentialStore(this.storage);

  static const _key = 'dalijob_guest_credential';
  final FlutterSecureStorage storage;

  @override
  Future<String?> read() => storage.read(key: _key);

  @override
  Future<void> write(String credential) =>
      storage.write(key: _key, value: credential);

  @override
  Future<void> clear() => storage.delete(key: _key);
}
