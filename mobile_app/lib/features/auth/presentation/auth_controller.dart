import 'package:flutter/material.dart';

import '../domain/auth_repository.dart';

class AuthController extends ChangeNotifier {
  final AuthRepository repository;
  bool loading = false;
  bool isAuthenticated = false;
  String? error;

  AuthController({required this.repository});

  Future<void> restoreSession() async {
    loading = true;
    notifyListeners();
    final result = await repository.restoreSession();
    isAuthenticated = result.data ?? false;
    loading = false;
    notifyListeners();
  }

  Future<bool> login(String username, String password) async {
    loading = true;
    error = null;
    notifyListeners();
    final result = await repository.login(username: username, password: password);
    loading = false;
    if (result.isSuccess) {
      isAuthenticated = true;
      notifyListeners();
      return true;
    }
    error = result.error;
    notifyListeners();
    return false;
  }

  Future<void> logout() async {
    await repository.logout();
    isAuthenticated = false;
    notifyListeners();
  }
}
