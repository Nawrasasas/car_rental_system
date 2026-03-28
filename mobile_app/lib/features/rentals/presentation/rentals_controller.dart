import 'package:flutter/material.dart';

import '../domain/rental.dart';
import '../domain/rentals_repository.dart';

class RentalsController extends ChangeNotifier {
  final RentalsRepository repository;
  RentalsController(this.repository);

  bool loading = false;
  String? error;
  List<Rental> rentals = [];

  Future<void> load() async {
    loading = true;
    error = null;
    notifyListeners();
    final result = await repository.fetchRentals();
    loading = false;
    if (result.isSuccess) {
      rentals = result.data ?? [];
    } else {
      error = result.error;
    }
    notifyListeners();
  }
}
