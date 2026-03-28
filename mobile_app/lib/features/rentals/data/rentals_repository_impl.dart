import '../../../core/constants/api_endpoints.dart';
import '../../../core/network/api_client.dart';
import '../../../core/utils/result.dart';
import '../domain/rental.dart';
import '../domain/rentals_repository.dart';

class RentalsRepositoryImpl implements RentalsRepository {
  final ApiClient _api;
  RentalsRepositoryImpl(this._api);

  @override
  Future<Result<List<Rental>>> fetchRentals() async {
    try {
      final response = await _api.get(ApiEndpoints.rentals);
      final raw = (response['results'] ?? response['data'] ?? []) as List<dynamic>;
      return Result.success(raw.map((e) => Rental.fromJson(e as Map<String, dynamic>)).toList());
    } catch (e) {
      return Result.failure(e.toString().replaceFirst('Exception: ', ''));
    }
  }

  @override
  Future<Result<Rental>> fetchRental(int id) async {
    try {
      final response = await _api.get('${ApiEndpoints.rentals}$id/');
      return Result.success(Rental.fromJson(response));
    } catch (e) {
      return Result.failure(e.toString().replaceFirst('Exception: ', ''));
    }
  }

  @override
  Future<Result<void>> createRental(Map<String, dynamic> payload) async {
    try {
      await _api.post(ApiEndpoints.rentals, payload);
      return Result.success(null);
    } catch (e) {
      return Result.failure(e.toString().replaceFirst('Exception: ', ''));
    }
  }
}
