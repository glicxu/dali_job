import '../api/api_client.dart';
import 'guest_models.dart';

class CreatedGuestTrial {
  const CreatedGuestTrial({required this.credential, required this.publicId});
  final String credential;
  final String publicId;
}

String _resumeContentType(String fileName) {
  final normalized = fileName.toLowerCase();
  if (normalized.endsWith('.pdf')) return 'application/pdf';
  if (normalized.endsWith('.docx')) {
    return 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';
  }
  return 'text/plain';
}

class GuestRepository {
  const GuestRepository(this.api);
  final ApiClient api;

  String _authorization(String credential) => 'Guest $credential';

  Future<CreatedGuestTrial> create() async {
    final json = await api.post('guest-trials');
    return CreatedGuestTrial(
      credential: json['guest_credential'] as String,
      publicId: json['public_id'] as String,
    );
  }

  Future<GuestTrialSnapshot> current(String credential) async {
    final trial = await api.get(
      'guest-trials/current',
      authorization: _authorization(credential),
    );
    final match = await api.get(
      'guest-trials/current/match',
      authorization: _authorization(credential),
    );
    return GuestTrialSnapshot.fromJson({...trial, 'match': match});
  }

  Future<Map<String, dynamic>> uploadResume(
    String credential, {
    required String fileName,
    required List<int> bytes,
  }) => api.postFile(
    'guest-trials/current/resume-import',
    fieldName: 'file',
    fileName: fileName,
    bytes: bytes,
    contentType: _resumeContentType(fileName),
    authorization: _authorization(credential),
  );

  Future<Map<String, dynamic>> retryResumeParse(String credential) => api.post(
    'guest-trials/current/resume-import/retry',
    authorization: _authorization(credential),
  );

  Future<void> confirmProfile(
    String credential,
    Map<String, dynamic> resumeData,
  ) async {
    await api.put(
      'guest-trials/current/profile',
      authorization: _authorization(credential),
      body: {'resume_data': resumeData},
    );
  }

  Future<void> saveCriteria(
    String credential, {
    required String keyword,
    required String location,
  }) async {
    await api.put(
      'guest-trials/current/criteria',
      authorization: _authorization(credential),
      body: {'keyword': keyword, 'location': location},
    );
  }

  Future<Map<String, dynamic>> startMatch(
    String credential,
    String idempotencyKey,
  ) => api.post(
    'guest-trials/current/match',
    authorization: _authorization(credential),
    extraHeaders: {'Idempotency-Key': idempotencyKey},
  );

  Future<Map<String, dynamic>> matchStatus(String credential) => api.get(
    'guest-trials/current/match',
    authorization: _authorization(credential),
  );

  Future<void> deleteTrial(String credential) => api.delete(
    'guest-trials/current',
    authorization: _authorization(credential),
  );
}
