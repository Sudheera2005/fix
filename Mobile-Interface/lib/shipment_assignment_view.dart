import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:url_launcher/url_launcher.dart';
import 'package:firebase_database/firebase_database.dart';
import 'package:geolocator/geolocator.dart';
import 'package:signature/signature.dart';
import 'qr_scanner_view.dart';
import 'package:shared_preferences/shared_preferences.dart';

class ShipmentAssignmentView extends StatefulWidget {
  final int userId;
  final String baseUrl;

  const ShipmentAssignmentView({
    super.key,
    required this.userId,
    required this.baseUrl,
  });

  @override
  State<ShipmentAssignmentView> createState() => _ShipmentAssignmentViewState();
}

class _ShipmentAssignmentViewState extends State<ShipmentAssignmentView> {
  Map<String, dynamic>? _data;
  bool _isLoading = true;
  String? _error;
  bool _missionCompleted = false;
  Timer? _acceptanceTimer;
  int _secondsRemaining = 900; // 15 minutes timeout
  StreamSubscription<Position>? _locationSubscription;
  bool _isTracking = false;
  FirebaseDatabase? _database;

  String? _accessToken;

  Map<String, String> get _authHeaders => {
    'Content-Type': 'application/json',
    if (_accessToken != null) 'Authorization': 'Bearer $_accessToken',
  };

  @override
  void initState() {
    super.initState();
    _loadTokenAndFetch();
  }

  Future<void> _loadTokenAndFetch() async {
    final prefs = await SharedPreferences.getInstance();
    _accessToken = prefs.getString('access_token');
    _fetchAssignment();
  }

  @override
  void dispose() {
    _acceptanceTimer?.cancel();
    _locationSubscription?.cancel();
    super.dispose();
  }

  void _startAcceptanceTimer() {
    _acceptanceTimer?.cancel();
    _secondsRemaining = 900;
    _acceptanceTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (_secondsRemaining > 0) {
        setState(() => _secondsRemaining--);
      } else {
        timer.cancel();
        _handleTimeout();
      }
    });
  }

  void _handleTimeout() {
    setState(() => _error = "Assignment Timeout: Escalating to dispatcher.");
    // In a real app, notify backend here
  }

  Future<void> _fetchAssignment() async {
    setState(() => _isLoading = true);
    try {
      final response = await http.get(
        Uri.parse("${widget.baseUrl}shipments/assignment_view/?user_id=${widget.userId}"),
        headers: _authHeaders,
      );

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        debugPrint("FETCHED ASSIGNMENT DATA: ${response.body}");
        
        if (data.containsKey('error')) {
          setState(() {
            _data = null;
            _error = data['error'];
          });
          return;
        }

        setState(() {
          _data = data;
          _error = null;
        });
        if (data['status'] == 'dispatched') {
          _startAcceptanceTimer();
        } else if (data['status'] == 'in_transit') {
          _startLocationTracking(data['shipment_id'].toString());
        }
      } else if (response.statusCode == 404) {
        setState(() {
          _data = null;
          _error = "No active assignments located for your ID.";
        });
      } else {
        setState(() => _error = "Network Error: Bridge status ${response.statusCode}");
      }
    } catch (e) {
      setState(() => _error = "Connection Sync Failure: Backend unreachable.");
    } finally {
      setState(() => _isLoading = false);
    }
  }

  Future<void> _startLocationTracking(String shipmentId) async {
    bool serviceEnabled = await Geolocator.isLocationServiceEnabled();
    if (!serviceEnabled) return;

    LocationPermission permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
      if (permission == LocationPermission.denied) return;
    }
    if (permission == LocationPermission.deniedForever) {
      // Permissions are denied forever, handle appropriately. 
      return;
    }

    _locationSubscription?.cancel();
    try {
      _database ??= FirebaseDatabase.instance;
      _locationSubscription = Geolocator.getPositionStream(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.high,
          distanceFilter: 30,
        ),
      ).listen((Position position) {
        try {
          _database!.ref("tracking/$shipmentId/current").set({
            "lat": position.latitude,
            "lng": position.longitude,
            "accuracy": position.accuracy,
            "timestamp": DateTime.now().toIso8601String(),
            "driver_id": widget.userId,
            "active": true,
          });
        } catch (e) {
          debugPrint("Firebase database update failed: \$e");
        }
      });
    } catch (e) {
      debugPrint("Failed to start Firebase tracking: \$e");
      _showError("Real-time tracking unavailable");
    }

  }

  Future<void> _stopTracking(String shipmentId) async {
    await _locationSubscription?.cancel();
    _locationSubscription = null;
    try {
      _database ??= FirebaseDatabase.instance;
      await _database!.ref("tracking/$shipmentId/current").update({"active": false});
    } catch (e) {
      debugPrint("Failed to stop tracking: \$e");
    }
  }


  Future<void> _acceptAssignment() async {
    if (_data == null) return;
    final id = _data!['shipment_id'];
    setState(() => _isLoading = true);
    try {
      final resp = await http.post(
        Uri.parse("${widget.baseUrl}shipments/$id/accept_assignment/"),
        headers: _authHeaders,
        body: jsonEncode({"user_id": widget.userId}),
      );
      if (resp.statusCode == 200) {
        _acceptanceTimer?.cancel();
        _fetchAssignment();
      } else {
        final body = jsonDecode(resp.body);
        final msg = body['error'] ?? "Failed to accept mission.";
        _showError(msg);
      }
    } catch (e) {
      _showError("Acceptance Failure: $e");
    } finally {
      setState(() => _isLoading = false);
    }
  }

  Future<void> _confirmPickup(String qrCode) async {
    if (_data == null) return;
    final id = _data!['shipment_id'];
    setState(() => _isLoading = true);
    try {
      final resp = await http.post(
        Uri.parse("${widget.baseUrl}shipments/$id/scan_pickup/"),
        headers: _authHeaders,
        body: jsonEncode({
          "qr_token": qrCode,
          "user_id": widget.userId
        }),
      );
      if (resp.statusCode == 200) {
        _fetchAssignment();
      } else {
        _showError(jsonDecode(resp.body)['error'] ?? "Invalid QR");
      }
    } catch (e) {
      _showError("Pickup Failure: $e");
    } finally {
      setState(() => _isLoading = false);
    }
  }

  Future<void> _completeDelivery(String orderId, String qrCode, {String? signature}) async {
    if (_data == null) return;
    final id = _data!['shipment_id'];
    
    setState(() => _isLoading = true);
    try {
      Position pos;
      try {
        pos = await Geolocator.getCurrentPosition();
      } catch (e) {
        // Fallback or rethrow
        throw Exception("Please enable GPS/Location Services to complete delivery.");
      }
      final resp = await http.post(
        Uri.parse("${widget.baseUrl}shipments/$id/scan_delivery/"),
        headers: _authHeaders,
        body: jsonEncode({
          "order_id": orderId,
          "qr_token": qrCode,
          "lat": pos.latitude,
          "lng": pos.longitude,
          "user_id": widget.userId,
          if (signature != null) "signature": signature
        }),
      );
      if (resp.statusCode == 200) {
        final result = jsonDecode(resp.body);
        if (result['is_completed'] == true) {
          _stopTracking(id);
          setState(() => _missionCompleted = true);
        } else {
          _fetchAssignment();
        }
      } else {
        _showError(jsonDecode(resp.body)['error'] ?? "Verification Error");
      }
    } catch (e) {
      _showError("Delivery Finalization Failure: $e");
    } finally {
      setState(() => _isLoading = false);
    }
  }
  
  void _showSignatureCapture(String orderId, String qrCode) {
    final signatureController = SignatureController(
      penStrokeWidth: 3,
      penColor: const Color(0xFF3E2723),
      exportBackgroundColor: Colors.white,
    );

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (context) => Container(
        height: MediaQuery.of(context).size.height * 0.8,
        decoration: const BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.vertical(top: Radius.circular(40)),
        ),
        padding: const EdgeInsets.all(32),
        child: Column(
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text("Recipient Signature", style: TextStyle(fontSize: 20, fontWeight: FontWeight.w900, color: Color(0xFF3E2723))),
                IconButton(icon: const Icon(Icons.close), onPressed: () => Navigator.pop(context)),
              ],
            ),
            const SizedBox(height: 8),
            const Text("Please have the recipient sign below to confirm delivery.", style: TextStyle(fontSize: 12, color: Color(0xFFBCAAA4))),
            const SizedBox(height: 32),
            Expanded(
              child: Container(
                decoration: BoxDecoration(
                  border: Border.all(color: const Color(0xFFEFEBE9), width: 2),
                  borderRadius: BorderRadius.circular(24),
                ),
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(22),
                  child: Signature(
                    controller: signatureController,
                    backgroundColor: Colors.white,
                  ),
                ),
              ),
            ),
            const SizedBox(height: 32),
            Row(
              children: [
                Expanded(child: _buildSecondaryButton(
                  label: "CLEAR", 
                  icon: Icons.refresh_rounded, 
                  onPressed: () => signatureController.clear()
                )),
                const SizedBox(width: 12),
                Expanded(child: _buildActionBtn(
                  label: "CONFIRM DELIVERY", 
                  color: const Color(0xFF3E2723), 
                  onPressed: () async {
                    if (signatureController.isEmpty) {
                       ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text("Signature is required to complete delivery.")));
                       return;
                    }
                    final signatureBytes = await signatureController.toPngBytes();
                    final base64Signature = base64Encode(signatureBytes!);
                    Navigator.pop(context);
                    await _completeDelivery(orderId, qrCode, signature: base64Signature);
                  }
                )),
              ],
            ),
          ],
        ),
      ),
    );
  }

  void _showError(String msg) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(msg),
      backgroundColor: Colors.redAccent,
    ));
  }

  _launchNavigation(String? address) async {
    if (address == null || address.isEmpty) {
      _showError("Invalid navigation address");
      return;
    }
    final url = "google.navigation:q=${Uri.encodeComponent(address)}&mode=d";

    if (await canLaunchUrl(Uri.parse(url))) {
      await launchUrl(Uri.parse(url));
    } else {
      final webUrl = "https://www.google.com/maps/dir/?api=1&destination=${Uri.encodeComponent(address)}";
      await launchUrl(Uri.parse(webUrl));
    }
  }

  String? _selectedStopAddress;
  String? _selectedStopOrderId;

  @override
  Widget build(BuildContext context) {
    if (_isLoading) {
      return const Scaffold(
        backgroundColor: Color(0xFFFCFBF9),
        body: Center(child: CircularProgressIndicator(color: Color(0xFF3E2723))),
      );
    }

    if (_error != null) { return _buildErrorState(); }
    if (_data == null) {
      return const Scaffold(
        backgroundColor: Color(0xFFFCFBF9),
        body: Center(child: CircularProgressIndicator(color: Color(0xFF3E2723))),
      );
    }

    final status = _data!['status'] ?? 'unknown';
    return Scaffold(
      backgroundColor: const Color(0xFFFCFBF9),
      appBar: AppBar(
        title: Column(
          children: [
            Text("ASSIGNMENT MF-${_data!['shipment_id']}", style: const TextStyle(fontWeight: FontWeight.w900, letterSpacing: 2, fontSize: 10, color: Colors.white70)),
            if (_data!['vehicle'] is Map)
              Text(
                "${_data!['vehicle']['plate_number']}",
                style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w900, color: Colors.white, letterSpacing: -0.5),
              ),
          ],
        ),
        backgroundColor: const Color(0xFF3E2723),
        elevation: 0,
        centerTitle: true,
        iconTheme: const IconThemeData(color: Colors.white),
        actions: [
          IconButton(icon: const Icon(Icons.refresh, color: Colors.white), onPressed: _fetchAssignment)
        ],
        shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(bottom: Radius.circular(24)),
        ),
      ),
      body: _buildBody(status),
    );
  }

  Widget _buildBody(String status) {
    if (_missionCompleted) return _buildFinalizedStage();
    switch (status) {
      case 'dispatched': return _buildAcceptanceStage();
      case 'accepted': return _buildPickupStage();
      case 'in_transit': return _buildTransitStage();
      case 'completed': return _buildFinalizedStage();
      default: return _buildTransitStage();
    }
  }

  // --- STAGE 1: MISSION ACCEPTANCE ---
  Widget _buildAcceptanceStage() {
    return Padding(
      padding: const EdgeInsets.all(32),
      child: Column(
        children: [
          const Spacer(),
          Container(
            padding: const EdgeInsets.all(40),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(40),
              boxShadow: [BoxShadow(color: Colors.black.withOpacity(0.05), blurRadius: 30)],
            ),
            child: const Icon(Icons.assignment_late_rounded, size: 80, color: Color(0xFF3E2723)),
          ),
          const SizedBox(height: 40),
          const Text("NEW MISSION ASSIGNED", style: TextStyle(fontSize: 22, fontWeight: FontWeight.w900, color: Color(0xFF3E2723), letterSpacing: -0.5)),
          const SizedBox(height: 12),
          Text(
            "${_data!['warehouse']['name']} → ${_data!['route_summary']['total_stops']} Stops",
            style: const TextStyle(fontSize: 14, fontWeight: FontWeight.bold, color: Color(0xFFBCAAA4)),
          ),
          const Spacer(),
          _buildPrimaryStickyButton(
            label: "ACCEPT MISSION",
            icon: Icons.check_circle_rounded,
            onPressed: _acceptAssignment,
            subtext: "Auto-escalation in ${(_secondsRemaining ~/ 60)}:${(_secondsRemaining % 60).toString().padLeft(2, '0')}",
          ),
        ],
      ),
    );
  }

  // --- STAGE 2: PICKUP FLOW ---
  Widget _buildPickupStage() {
    final wh = _data!['warehouse'];
    return Padding(
      padding: const EdgeInsets.all(32),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _buildStepHeader(1, "ARRIVE AT PICKUP"),
          const SizedBox(height: 24),
          _buildLocationCard(wh['name'], wh['address'], Icons.warehouse_rounded),
          const Spacer(),
          _buildPrimaryStickyButton(
            label: "NAVIGATE TO WAREHOUSE",
            icon: Icons.navigation_rounded,
            onPressed: () => _launchNavigation(wh['address']),
          ),
          const SizedBox(height: 16),
          _buildSecondaryButton(
            label: "SCAN PICKUP QR",
            icon: Icons.qr_code_scanner_rounded,
            onPressed: () {
              bool hasScanned = false;
              Navigator.push(context, MaterialPageRoute(builder: (scanCtx) => QRScannerView(
                title: "Scan Pickup",
                onScan: (code) async {
                  if (hasScanned) return;
                  hasScanned = true;
                  Navigator.pop(scanCtx);
                  await _confirmPickup(code);
                },
              )));
            },
          ),
        ],
      ),
    );
  }

  // --- STAGE 3: TRANSIT / DELIVERY FLOW ---
  Widget _buildTransitStage() {
    final allStops = _data!['stops'] as List;
    debugPrint("REBUILDING TRANSIT STAGE. TOTAL STOPS: ${allStops.length}");
    final pendingStops = allStops.where((s) {
      final status = (s['status'] ?? '').toString().toLowerCase();
      debugPrint("STOP ID ${s['order_id']} STATUS: $status");
      return status != 'delivered' && status != 'delivery_failed';
    }).toList();
    debugPrint("PENDING STOPS FILTERED: ${pendingStops.length}");
    
    return Column(
      children: [
        // Mini Map/Stats Area
        Container(
          padding: const EdgeInsets.symmetric(vertical: 20, horizontal: 32),
          color: const Color(0xFF3E2723).withOpacity(0.03),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              _buildMiniStat("${pendingStops.length}", "REMAINING"),
              _buildMiniStat("${_data!['route_summary']['total_distance_km']}", "KM"),
              _buildMiniStat("${_data!['route_summary']['estimated_duration_minutes']}", "ETA"),
            ],
          ),
        ),
        
        Expanded(
          child: RefreshIndicator(
            onRefresh: _fetchAssignment,
            color: const Color(0xFF3E2723),
            child: ListView.builder(
              padding: const EdgeInsets.all(32),
              itemCount: pendingStops.length,
              itemBuilder: (context, index) {
                final stop = pendingStops[index];
                return _buildFieldStopCard(stop);
              },
            ),
          ),
        ),

        // Contextual Floating Action
        _buildPrimaryStickyButton(
          label: "SCAN DELIVERY",
          icon: Icons.qr_code_scanner_rounded,
          onPressed: () {
              // Usually, driver should select a stop first or scan any item
              ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text("Expand a stop and click DELIVER to authenticate."), behavior: SnackBarBehavior.floating));
          },
        ),
      ],
    );
  }

  Widget _buildFieldStopCard(Map<String, dynamic> stop) {
    return Container(
      margin: const EdgeInsets.only(bottom: 20),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(30),
        border: Border.all(color: const Color(0xFFEFEBE9)),
      ),
      child: ExpansionTile(
        tilePadding: const EdgeInsets.symmetric(horizontal: 24, vertical: 8),
        shape: const RoundedRectangleBorder(borderRadius: BorderRadius.all(Radius.circular(30))),
        leading: CircleAvatar(
          backgroundColor: const Color(0xFF3E2723).withOpacity(0.05),
          child: Text("${stop['sequence']}", style: const TextStyle(fontWeight: FontWeight.w900, color: Color(0xFF3E2723))),
        ),
        title: Text(stop['address'], style: const TextStyle(fontWeight: FontWeight.w900, fontSize: 15, color: Color(0xFF3E2723))),
        subtitle: Text("PARCELS: ${stop['parcels']} • KG: ${stop['weight_kg']}", style: const TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: Color(0xFFBCAAA4))),
        children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(24, 0, 24, 24),
              child: Column(
                children: [
                  Row(
                    children: [
                      Expanded(child: _buildSecondaryButton(
                        label: "NAVIGATE",
                        icon: Icons.navigation_rounded,
                        onPressed: () => _launchNavigation(stop['address']),
                      )),
                      const SizedBox(width: 12),
                      Expanded(child: _buildActionBtn(
                        label: "DELIVER",
                        color: const Color(0xFF3E2723),
                        onPressed: () {
                          bool hasScanned = false;
                          Navigator.push(context, MaterialPageRoute(builder: (scanCtx) => QRScannerView(
                            title: "Deliver Stop",
                            onScan: (code) async {
                              if (hasScanned) return;
                              hasScanned = true;
                              Navigator.pop(scanCtx);
                              _showSignatureCapture(stop['order_id'], code);
                            },
                          )));
                        },
                      )),
                    ],
                  ),
                  const SizedBox(height: 12),
                  _buildIssueButton(
                    onPressed: () => _showExceptionDialog(stop['order_id']),
                  ),
                ],
              ),
            )
        ],
      ),
    );
  }

  Widget _buildIssueButton({required VoidCallback onPressed}) {
    return OutlinedButton(
      onPressed: onPressed,
      style: OutlinedButton.styleFrom(
        minimumSize: const Size(double.infinity, 50),
        side: const BorderSide(color: Colors.redAccent, width: 1.5),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      ),
      child: const Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(Icons.report_problem_rounded, color: Colors.redAccent, size: 18),
          SizedBox(width: 8),
          Text("REPORT ISSUE / EXCEPTION", style: TextStyle(fontSize: 11, fontWeight: FontWeight.w900, color: Colors.redAccent, letterSpacing: 1)),
        ],
      ),
    );
  }

  void _showExceptionDialog(String orderId) {
    String? selectedReason = 'damaged_goods';
    final notesController = TextEditingController();

    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text("Report Delivery Issue", style: TextStyle(fontWeight: FontWeight.w900)),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            DropdownButtonFormField<String>(
              value: selectedReason,
              items: const [
                DropdownMenuItem(value: 'damaged_goods', child: Text("Damaged Goods")),
                DropdownMenuItem(value: 'no_answer', child: Text("Recipient Not Available")),
                DropdownMenuItem(value: 'refused', child: Text("Delivery Refused")),
                DropdownMenuItem(value: 'address_not_found', child: Text("Address Issues")),
                DropdownMenuItem(value: 'other', child: Text("Other / Mechanical")),
              ],
              onChanged: (v) => selectedReason = v,
              decoration: const InputDecoration(labelText: "Reason"),
            ),
            TextField(
              controller: notesController,
              decoration: const InputDecoration(labelText: "Additional Notes"),
              maxLines: 2,
            ),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text("CANCEL")),
          ElevatedButton(
            onPressed: () async {
              Navigator.pop(context);
              await _reportException(orderId, selectedReason!, notesController.text);
            },
            style: ElevatedButton.styleFrom(backgroundColor: Colors.redAccent),
            child: const Text("SUBMIT REPORT", style: TextStyle(color: Colors.white)),
          ),
        ],
      ),
    );
  }

  Future<void> _reportException(String orderId, String type, String notes) async {
    setState(() => _isLoading = true);
    try {
      Position pos;
      try {
        pos = await Geolocator.getCurrentPosition();
      } catch (e) {
        throw Exception("Please enable GPS/Location Services to report an issue.");
      }
      final resp = await http.post(
        Uri.parse("${widget.baseUrl}orders/$orderId/report_exception/"),
        headers: _authHeaders,
        body: jsonEncode({
          "exception_type": type,
          "notes": notes,
          "lat": pos.latitude,
          "lng": pos.longitude,
        }),
      );
      if (resp.statusCode == 200) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text("Issue logged and reported to dispatch."), backgroundColor: Colors.orange));
        _fetchAssignment();
      } else {
        _showError("Failed to report issue");
      }
    } catch (e) {
      _showError("Connection error during reporting");
    } finally {
      setState(() => _isLoading = false);
    }
  }

  // --- STAGE 4: COMPLETION ---
  Widget _buildFinalizedStage() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(40),
        child: Column(
          children: [
            const Spacer(),
            Container(
              padding: const EdgeInsets.all(40),
              decoration: const BoxDecoration(color: Color(0xFF4CAF50), shape: BoxShape.circle),
              child: const Icon(Icons.check_rounded, size: 60, color: Colors.white),
            ),
            const SizedBox(height: 32),
            const Text("MISSION SUCCESS", style: TextStyle(fontSize: 24, fontWeight: FontWeight.w900, color: Color(0xFF3E2723))),
            const SizedBox(height: 12),
            const Text("All stops verified. Report to terminal.", textAlign: TextAlign.center, style: TextStyle(fontWeight: FontWeight.bold, color: Color(0xFFBCAAA4))),
            const Spacer(),
            _buildPrimaryStickyButton(label: "CLOSE MISSION", icon: Icons.home_rounded, onPressed: () => Navigator.pop(context)),
          ],
        ),
      ),
    );
  }

  // --- UI COMPONENTS ---
  Widget _buildStepHeader(int step, String title) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text("STEP $step / 4", style: TextStyle(fontSize: 10, fontWeight: FontWeight.w900, color: const Color(0xFFBCAAA4), letterSpacing: 2)),
        const SizedBox(height: 4),
        Text(title, style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w900, color: Color(0xFF3E2723), letterSpacing: -0.5)),
      ],
    );
  }

  Widget _buildLocationCard(String title, String address, IconData icon) {
    return Container(
      padding: const EdgeInsets.all(32),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(40),
        border: Border.all(color: const Color(0xFFEFEBE9)),
      ),
      child: Row(
        children: [
          Icon(icon, size: 32, color: const Color(0xFF8D6E63)),
          const SizedBox(width: 24),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w900, color: Color(0xFF3E2723))),
                const SizedBox(height: 8),
                Text(address, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: Color(0xFFBCAAA4))),
              ],
            ),
          )
        ],
      ),
    );
  }

  Widget _buildPrimaryStickyButton({required String label, required IconData icon, required VoidCallback onPressed, String? subtext}) {
    return Container(
      padding: const EdgeInsets.all(24),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (subtext != null)
             Padding(padding: const EdgeInsets.only(bottom: 12), child: Text(subtext, style: const TextStyle(fontSize: 10, fontWeight: FontWeight.w900, color: Color(0xFF8D6E63), letterSpacing: 1))),
          ElevatedButton(
            onPressed: onPressed,
            style: ElevatedButton.styleFrom(
              backgroundColor: const Color(0xFF3E2723),
              minimumSize: const Size(double.infinity, 80),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
              elevation: 10,
              shadowColor: const Color(0xFF3E2723).withOpacity(0.3),
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(icon, color: Colors.white, size: 28),
                const SizedBox(width: 16),
                Text(label, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w900, color: Colors.white, letterSpacing: 1)),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSecondaryButton({required String label, required IconData icon, required VoidCallback onPressed}) {
    return OutlinedButton(
      onPressed: onPressed,
      style: OutlinedButton.styleFrom(
        minimumSize: const Size(double.infinity, 70),
        side: const BorderSide(color: Color(0xFF3E2723), width: 2),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(icon, color: const Color(0xFF3E2723), size: 24),
          const SizedBox(width: 12),
          Text(label, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w900, color: Color(0xFF3E2723), letterSpacing: 1)),
        ],
      ),
    );
  }

  Widget _buildActionBtn({required String label, required Color color, required VoidCallback onPressed}) {
    return ElevatedButton(
      onPressed: onPressed,
      style: ElevatedButton.styleFrom(backgroundColor: color, minimumSize: const Size(double.infinity, 60), shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16))),
      child: Text(label, style: const TextStyle(fontWeight: FontWeight.w900, color: Colors.white)),
    );
  }

  Widget _buildMiniStat(String value, String label) {
    return Column(
      children: [
        Text(value, style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w900, color: Color(0xFF3E2723))),
        Text(label, style: const TextStyle(fontSize: 9, fontWeight: FontWeight.w900, color: Color(0xFFBCAAA4), letterSpacing: 1)),
      ],
    );
  }

  Widget _buildErrorState() {
     return Scaffold(
      backgroundColor: const Color(0xFFFCFBF9),
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.error_outline_rounded, size: 80, color: Color(0xFFD7CCC8)),
            const SizedBox(height: 24),
            Text(_error!, textAlign: TextAlign.center, style: const TextStyle(fontWeight: FontWeight.bold, color: Color(0xFFBCAAA4))),
            const SizedBox(height: 40),
            _buildActionBtn(label: "RELOAD SYNC", color: const Color(0xFF3E2723), onPressed: _fetchAssignment),
          ],
        ),
      ),
     );
  }
}
