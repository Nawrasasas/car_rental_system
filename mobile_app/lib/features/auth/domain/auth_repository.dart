import '../../../core/utils/result.dart';

abstract class AuthRepository {
  Future<Result<void>> login({required String username, required String password});
  Future<Result<bool>> restoreSession();
  Future<void> logout();
}
