import 'dart:convert';

import 'package:http/http.dart' as http;

import 'api_exception.dart';

class ApiClient {
  ApiClient(this.baseUrl, this.httpClient);

  final Uri baseUrl;
  final http.Client httpClient;

  Future<Map<String, dynamic>> post(
    String path, {
    Map<String, dynamic>? body,
    String? accessToken,
  }) async {
    final response = await httpClient.post(
      baseUrl.resolve(path),
      headers: _headers(accessToken),
      body: jsonEncode(body ?? const <String, dynamic>{}),
    );
    return _decode(response);
  }

  Future<void> delete(String path, {required String accessToken}) async {
    final response = await httpClient.delete(
      baseUrl.resolve(path),
      headers: _headers(accessToken),
    );
    if (response.statusCode < 200 || response.statusCode >= 300) {
      _throwResponse(response);
    }
  }

  Map<String, String> _headers(String? accessToken) => {
    'Accept': 'application/json',
    'Content-Type': 'application/json',
    if (accessToken != null) 'Authorization': 'Bearer $accessToken',
  };

  Map<String, dynamic> _decode(http.Response response) {
    if (response.statusCode < 200 || response.statusCode >= 300) {
      _throwResponse(response);
    }
    if (response.body.isEmpty) return const {};
    final decoded = jsonDecode(response.body);
    if (decoded is! Map<String, dynamic>) {
      throw const ApiException('The server returned an invalid response.');
    }
    return decoded;
  }

  Never _throwResponse(http.Response response) {
    var message = 'Request failed. Please try again.';
    try {
      final decoded = jsonDecode(response.body);
      if (decoded is Map && decoded['detail'] is String) {
        message = decoded['detail'] as String;
      }
    } on FormatException {
      // Keep the safe fallback; never surface an HTML or proxy error body.
    }
    throw ApiException(message, statusCode: response.statusCode);
  }
}
