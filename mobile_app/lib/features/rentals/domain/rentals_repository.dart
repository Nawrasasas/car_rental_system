import '../../../core/utils/result.dart';
import 'rental.dart';

abstract class RentalsRepository {
  Future<Result<List<Rental>>> fetchRentals();
  Future<Result<Rental>> fetchRental(int id);
  Future<Result<void>> createRental(Map<String, dynamic> payload);
}
