import 'dart:convert';

import 'package:http/http.dart' as http;

class ApiClient {
  final String baseUrl;
  String? _token;

  ApiClient({required this.baseUrl});

  void setToken(String? token) => _token = token;

  Map<String, String> get _headers => {
        'Content-Type': 'application/json',
        if (_token != null) 'Authorization': 'Bearer $_token',
      };

  Future<Map<String, dynamic>> get(String path) async {
    final response = await http.get(Uri.parse('$baseUrl$path'), headers: _headers);
    return _process(response);
  }

  Future<Map<String, dynamic>> post(String path, Map<String, dynamic> body) async {
    final response = await http.post(
      Uri.parse('$baseUrl$path'),
      headers: _headers,
      body: jsonEncode(body),
    );
    return _process(response);
  }

  Map<String, dynamic> _process(http.Response response) {
    final raw = response.body.isNotEmpty ? jsonDecode(response.body) : <String, dynamic>{};
    if (response.statusCode >= 200 && response.statusCode < 300) {
      if (raw is Map<String, dynamic>) return raw;
      return {'results': raw};
    }
    throw Exception(
      raw is Map<String, dynamic>
          ? (raw['detail']?.toString() ?? 'API error ${response.statusCode}')
          : 'API error ${response.statusCode}',
    );
  }
}
