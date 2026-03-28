import '../../../core/constants/api_endpoints.dart';
import '../../../core/network/api_client.dart';
import '../../../core/storage/token_storage.dart';
import '../../../core/utils/result.dart';
import '../domain/auth_repository.dart';

class AuthRepositoryImpl implements AuthRepository {
  final ApiClient _api;
  final TokenStorage _storage;

  AuthRepositoryImpl(this._api, this._storage);

  @override
  Future<Result<void>> login({required String username, required String password}) async {
    try {
      final response = await _api.post(ApiEndpoints.login, {
        'username': username,
        'password': password,
      });
      final token = response['access']?.toString();
      if (token == null || token.isEmpty) {
        return Result.failure('Login succeeded but no token returned from API.');
      }
      _api.setToken(token);
      await _storage.saveToken(token);
      return Result.success(null);
    } catch (e) {
      return Result.failure(e.toString().replaceFirst('Exception: ', ''));
    }
  }

  @override
  Future<Result<bool>> restoreSession() async {
    final token = await _storage.readToken();
    if (token == null || token.isEmpty) return Result.success(false);
    _api.setToken(token);
    return Result.success(true);
  }

  @override
  Future<void> logout() async {
    _api.setToken(null);
    await _storage.clear();
  }
}
