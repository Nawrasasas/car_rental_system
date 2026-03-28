class Vehicle {
  final int id;
  final String plateNumber;
  final String name;
  final String status;
  final double dailyPrice;

  Vehicle({
    required this.id,
    required this.plateNumber,
    required this.name,
    required this.status,
    required this.dailyPrice,
  });

  factory Vehicle.fromJson(Map<String, dynamic> json) => Vehicle(
        id: json['id'] as int,
        plateNumber: json['plate_number']?.toString() ?? '-',
        name: '${json['brand'] ?? ''} ${json['model'] ?? ''}'.trim(),
        status: json['status']?.toString() ?? '-',
        dailyPrice: double.tryParse(json['daily_price']?.toString() ?? json['daily_rate']?.toString() ?? '0') ?? 0,
      );
}
