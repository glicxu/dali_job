import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';

import 'api_exception.dart';

class ApiClient {
  ApiClient(this.baseUrl, this.httpClient);

  final Uri baseUrl;
  final http.Client httpClient;

  Future<Map<String, dynamic>> get(
    String path, {
    String? accessToken,
    String? authorization,
  }) async {
    final response = await httpClient.get(
      baseUrl.resolve(path),
      headers: _headers(accessToken, authorization: authorization),
    );
    return _decode(response);
  }

  Future<Map<String, dynamic>> post(
    String path, {
    Map<String, dynamic>? body,
    String? accessToken,
    String? authorization,
    Map<String, String>? extraHeaders,
  }) async {
    final response = await httpClient.post(
      baseUrl.resolve(path),
      headers: {
        ..._headers(accessToken, authorization: authorization),
        ...?extraHeaders,
      },
      body: jsonEncode(body ?? const <String, dynamic>{}),
    );
    return _decode(response);
  }

  Future<void> delete(
    String path, {
    String? accessToken,
    String? authorization,
  }) async {
    final response = await httpClient.delete(
      baseUrl.resolve(path),
      headers: _headers(accessToken, authorization: authorization),
    );
    if (response.statusCode < 200 || response.statusCode >= 300) {
      _throwResponse(response);
    }
  }

  Future<Map<String, dynamic>> put(
    String path, {
    required Map<String, dynamic> body,
    String? accessToken,
    String? authorization,
  }) async {
    final response = await httpClient.put(
      baseUrl.resolve(path),
      headers: _headers(accessToken, authorization: authorization),
      body: jsonEncode(body),
    );
    return _decode(response);
  }

  Future<Map<String, dynamic>> patch(
    String path, {
    required Map<String, dynamic> body,
    String? accessToken,
  }) async {
    final response = await httpClient.patch(
      baseUrl.resolve(path),
      headers: _headers(accessToken),
      body: jsonEncode(body),
    );
    return _decode(response);
  }

  Future<Map<String, dynamic>> postFile(
    String path, {
    required String fieldName,
    required String fileName,
    required List<int> bytes,
    required String contentType,
    String? accessToken,
    String? authorization,
  }) async {
    final request = http.MultipartRequest('POST', baseUrl.resolve(path))
      ..headers.addAll({
        'Accept': 'application/json',
        if (authorization != null)
          'Authorization': authorization
        else if (accessToken != null)
          'Authorization': 'Bearer $accessToken',
      })
      ..files.add(
        http.MultipartFile.fromBytes(
          fieldName,
          bytes,
          filename: fileName,
          contentType: MediaType.parse(contentType),
        ),
      );
    final streamed = await httpClient.send(request);
    return _decode(await http.Response.fromStream(streamed));
  }

  Map<String, String> _headers(String? accessToken, {String? authorization}) =>
      {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        if (authorization != null)
          'Authorization': authorization
        else if (accessToken != null)
          'Authorization': 'Bearer $accessToken',
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
      } else if (decoded is Map && decoded['detail'] is Map) {
        final detail = decoded['detail'] as Map;
        if (detail['message'] is String) message = detail['message'] as String;
      }
    } on FormatException {
      // Keep the safe fallback; never surface an HTML or proxy error body.
    }
    throw ApiException(message, statusCode: response.statusCode);
  }
}
