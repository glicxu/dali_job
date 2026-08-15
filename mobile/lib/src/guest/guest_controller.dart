import 'dart:math';

import 'package:flutter/foundation.dart';

import '../api/api_exception.dart';
import '../auth/token_store.dart';
import 'guest_models.dart';
import 'guest_repository.dart';

enum GuestStatus { bootstrapping, none, active }

class GuestController extends ChangeNotifier {
  GuestController({required this.repository, required this.credentialStore});

  final GuestRepository repository;
  final GuestCredentialStore credentialStore;

  GuestStatus status = GuestStatus.bootstrapping;
  GuestTrialSnapshot? snapshot;
  String? credential;
  bool preferRegistration = false;
  bool busy = false;
  String? error;

  Future<void> bootstrap() async {
    final saved = await credentialStore.read();
    if (saved == null) {
      status = GuestStatus.none;
      notifyListeners();
      return;
    }
    credential = saved;
    try {
      snapshot = await repository.current(saved);
      status = GuestStatus.active;
    } on ApiException catch (exception) {
      if (exception.statusCode == 401) {
        await credentialStore.clear();
        credential = null;
      } else {
        error = exception.message;
      }
      status = GuestStatus.none;
    }
    notifyListeners();
  }

  Future<void> start() async => _run(() async {
    final created = await repository.create();
    credential = created.credential;
    await credentialStore.write(created.credential);
    snapshot = await repository.current(created.credential);
    status = GuestStatus.active;
  });

  Future<Map<String, dynamic>?> uploadResume(
    String fileName,
    List<int> bytes,
  ) async {
    Map<String, dynamic>? imported;
    await _run(() async {
      imported = await repository.uploadResume(
        credential!,
        fileName: fileName,
        bytes: bytes,
      );
      await refresh();
    });
    return imported;
  }

  Future<Map<String, dynamic>?> retryResumeParse() async {
    Map<String, dynamic>? imported;
    await _run(() async {
      imported = await repository.retryResumeParse(credential!);
      await refresh();
    });
    return imported;
  }

  Future<void> importAndConfirmProfile(String fileName, List<int> bytes) =>
      _run(() async {
        final imported = await repository.uploadResume(
          credential!,
          fileName: fileName,
          bytes: bytes,
        );
        final suggestions = imported['suggestions'];
        if (suggestions is Map && suggestions.isNotEmpty) {
          await repository.confirmProfile(
            credential!,
            Map<String, dynamic>.from(suggestions),
          );
        }
        await refresh();
      });

  Future<void> retryAndConfirmResumeParse() => _run(() async {
    final imported = await repository.retryResumeParse(credential!);
    final suggestions = imported['suggestions'];
    if (suggestions is Map && suggestions.isNotEmpty) {
      await repository.confirmProfile(
        credential!,
        Map<String, dynamic>.from(suggestions),
      );
    }
    await refresh();
  });

  Future<void> confirmProfile(Map<String, dynamic> resumeData) =>
      _run(() async {
        await repository.confirmProfile(credential!, resumeData);
        await refresh();
      });

  Future<void> saveCriteria(String keyword, String location) => _run(() async {
    await repository.saveCriteria(
      credential!,
      keyword: keyword,
      location: location,
    );
    await refresh();
  });

  Future<void> startMatch() => _run(() async {
    final key =
        '${DateTime.now().microsecondsSinceEpoch}-${Random.secure().nextInt(1 << 32)}';
    final match = await repository.startMatch(credential!, key);
    snapshot = snapshot?.withMatch(match);
  });

  Future<void> refresh() async {
    snapshot = await repository.current(credential!);
  }

  Future<void> deleteTrial() => _run(() async {
    await repository.deleteTrial(credential!);
    await credentialStore.clear();
    credential = null;
    snapshot = null;
    status = GuestStatus.none;
  });

  Future<void> leaveForSignIn() async {
    preferRegistration = false;
    status = GuestStatus.none;
    notifyListeners();
  }

  Future<void> leaveForRegistration() async {
    preferRegistration = true;
    status = GuestStatus.none;
    notifyListeners();
  }

  Future<void> resumeTrial() async {
    if (credential == null) return;
    await _run(() async {
      await refresh();
      status = GuestStatus.active;
    });
  }

  Future<void> _run(Future<void> Function() action) async {
    if (busy) return;
    busy = true;
    error = null;
    notifyListeners();
    try {
      await action();
    } catch (exception) {
      error = exception.toString();
    } finally {
      busy = false;
      notifyListeners();
    }
  }
}
