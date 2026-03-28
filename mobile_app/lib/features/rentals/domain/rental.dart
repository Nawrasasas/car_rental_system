class Rental {
  final int id;
  final String contractNumber;
  final String customerName;
  final String vehicleLabel;
  final String status;
  final String startDate;
  final String endDate;
  final double netTotal;

  Rental({
    required this.id,
    required this.contractNumber,
    required this.customerName,
    required this.vehicleLabel,
    required this.status,
    required this.startDate,
    required this.endDate,
    required this.netTotal,
  });

  factory Rental.fromJson(Map<String, dynamic> json) => Rental(
        id: json['id'] as int,
        contractNumber: json['contract_number']?.toString() ?? '#${json['id']}',
        customerName: json['customer_name']?.toString() ?? json['customer']?.toString() ?? '-',
        vehicleLabel: json['vehicle_label']?.toString() ?? json['vehicle']?.toString() ?? '-',
        status: json['status']?.toString() ?? '-',
        startDate: json['start_date']?.toString() ?? '-',
        endDate: json['end_date']?.toString() ?? '-',
        netTotal: double.tryParse(json['net_total']?.toString() ?? '0') ?? 0,
      );
}
