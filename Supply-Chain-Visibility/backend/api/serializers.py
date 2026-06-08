from rest_framework import serializers
from .models import CustomUser, Role, VehicleAssignment, Employee, Customer, Order, AuditLog, Shipment, ShipmentOrder, OrderException, OrderStatusLog, ProofOfDelivery
from vehicles.models import Vehicle
from drivers.models import Driver as DriverProfile

class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = ('business_name', 'contact_person_name', 'phone_number', 'alternate_phone', 'address', 'latitude', 'longitude', 'tax_id', 'credit_limit', 'payment_terms')

class DriverProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = DriverProfile
        fields = ('license_number', 'license_expiry_date', 'license_type', 'experience_years')

    def validate_license_number(self, value):
        if value in ["123", "abc", "test", "none"]:
            raise serializers.ValidationError("Please provide a valid License ID.")
        return value

    def validate_license_expiry_date(self, value):
        from datetime import date
        if value < date.today():
            raise serializers.ValidationError("Driver license has already expired.")
        return value

class EmployeeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Employee
        fields = ('full_name', 'national_id', 'contact_number', 'address', 'date_of_birth')

    def validate_national_id(self, value):
        import re
        if value == 'N/A':
            return value
        # Format: 9 digits + V/v OR 12 digits
        if not (re.match(r'^\d{9}[Vv]$', value) or re.match(r'^\d{12}$', value)):
            raise serializers.ValidationError("National ID must be 9 digits + 'V' or 12 digits.")
        return value

    def validate_contact_number(self, value):
        import re
        if value == 'N/A':
            return value
        if not re.match(r'^\d{10,}$', value):
            raise serializers.ValidationError("Telephone must be at least 10 digits.")
        return value

    def validate_date_of_birth(self, value):
        from datetime import date
        today = date.today()
        age = today.year - value.year - ((today.month, today.day) < (value.month, value.day))
        if age < 18:
            raise serializers.ValidationError("User must be at least 18 years old.")
        return value

class UserSerializer(serializers.ModelSerializer):
    id = serializers.ReadOnlyField()
    role = serializers.SerializerMethodField()
    role_id = serializers.IntegerField(write_only=True, required=False)
    status = serializers.SerializerMethodField()
    is_active = serializers.BooleanField(required=False)
    driver_profile = DriverProfileSerializer(required=False)
    employee = EmployeeSerializer(required=False, source='employee_profile')
    customer = CustomerSerializer(required=False, source='customer_profile')
    
    class Meta:
        model = CustomUser
        fields = ('id', 'username', 'email', 'password', 'role', 'role_id', 'status', 'is_active', 'driver_profile', 'employee', 'customer')
        extra_kwargs = {'password': {'write_only': True}}
        
    def get_role(self, obj):
        try:
            return obj.role.role_name.lower()
        except:
            return 'driver'
            
    def get_status(self, obj):
        return 'active' if obj.is_active else 'inactive'

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        try:
            if str(instance.role).lower() == 'driver' and hasattr(instance, 'employee_profile') and hasattr(instance.employee_profile, 'driver_profile'):
                ret['driver_profile'] = DriverProfileSerializer(instance.employee_profile.driver_profile).data
        except:
            pass
        return ret

    def create(self, validated_data):
        driver_profile_data = validated_data.pop('driver_profile', None)
        employee_data = validated_data.pop('employee_profile', None)
        customer_data = validated_data.pop('customer_profile', None)
        role_id = validated_data.pop('role_id', None)
        
        # In case the frontend sends "role" as an extra field in the view request (it might be dropped by the serializer)
        # We need a way to get the role string. For now, since it receives role_id optionally or drops 'role',
        # let's assume the View passes it in self.initial_data.
        role_str = self.initial_data.get('role', 'driver').lower()
        role_obj = Role.objects.filter(role_name__iexact=role_str).first()
        
        if role_obj:
            role_id = role_obj.role_id
            validated_data['role'] = role_obj
            role_name = role_str
        else:
            role_name = 'driver'
            
        user = CustomUser.objects.create_user(**validated_data)
                    
        if role_name == 'customer':
            if customer_data:
                Customer.objects.create(user=user, email=user.email, **customer_data)
            else:
                Customer.objects.create(user=user, email=user.email, phone_number='N/A', address='N/A')
        else:
            if employee_data:
                employee = Employee.objects.create(user=user, **employee_data)
            else:
                employee = Employee.objects.create(user=user, full_name=user.username, national_id='N/A', contact_number='N/A', address='N/A', date_of_birth='2000-01-01')
                
            if role_name == 'driver' and driver_profile_data:
                DriverProfile.objects.create(employee=employee, **driver_profile_data)
            
        return user

    def update(self, instance, validated_data):
        employee_data = validated_data.pop('employee_profile', None)
        customer_data = validated_data.pop('customer_profile', None)
        driver_profile_data = validated_data.pop('driver_profile', None)
        
        # Manually extract status active switch
        if 'is_active' in validated_data:
            instance.is_active = validated_data['is_active']
            
        # Standard user update
        for attr, value in validated_data.items():
            if attr == 'password':
                instance.set_password(value)
            else:
                setattr(instance, attr, value)
        instance.save()
        
        try:
            role_name = instance.role.role_name.lower()
        except:
            role_name = 'driver'
            
        if role_name == 'customer':
            if customer_data:
                customer, _ = Customer.objects.get_or_create(user=instance, defaults={'email': instance.email, 'phone_number': 'N/A', 'address': 'N/A'})
                for attr, value in customer_data.items():
                    setattr(customer, attr, value)
                customer.save()
        else:
            if employee_data:
                employee, _ = Employee.objects.get_or_create(user=instance, defaults={'full_name': instance.username, 'national_id': 'N/A', 'contact_number': 'N/A', 'address': 'N/A', 'date_of_birth': '2000-01-01'})
                for attr, value in employee_data.items():
                    setattr(employee, attr, value)
                employee.save()
            
            # CRITICAL: Ensure Driver records exist for driver role transition
            if str(instance.role).lower() == 'driver':
                employee, _ = Employee.objects.get_or_create(user=instance, defaults={'full_name': instance.username, 'national_id': 'N/A', 'contact_number': 'N/A', 'address': 'N/A', 'date_of_birth': '2000-01-01'})
                if not hasattr(employee, 'driver_profile'):
                    DriverProfile.objects.create(
                        employee=employee,
                        license_number='PENDING-UPDATE',
                        license_expiry_date='2099-12-31',
                        license_type='heavy_vehicle'
                    )
                
                if driver_profile_data and hasattr(employee, 'driver_profile'):
                    for attr, value in driver_profile_data.items():
                        setattr(employee.driver_profile, attr, value)
                    employee.driver_profile.save()
            
        return instance

class MaintenanceLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vehicle.maintenance_logs.rel.model if hasattr(Vehicle, 'maintenance_logs') else None # Late bind helper
        # Actually I just added them to vehicles.models so I should import them
        from vehicles.models import MaintenanceLog, FuelExpense
        model = MaintenanceLog
        fields = '__all__'

class FuelExpenseSerializer(serializers.ModelSerializer):
    class Meta:
        from vehicles.models import FuelExpense
        model = FuelExpense
        fields = '__all__'

class VehicleSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source='vehicle_id', read_only=True)
    plate_number = serializers.CharField()
    vehicle_type = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    make_model = serializers.CharField(source='model', required=False, allow_null=True, allow_blank=True)
    manufacturer = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    year = serializers.IntegerField(required=False, allow_null=True)
    capacity = serializers.FloatField(source='capacity_kg', required=False, allow_null=True)
    volume = serializers.FloatField(source='capacity_volume', required=False, allow_null=True)
    assignedDriver = serializers.SerializerMethodField()
    driver_name = serializers.SerializerMethodField()
    insurance_expiry = serializers.DateField(required=False, allow_null=True)
    registration_expiry = serializers.DateField(required=False, allow_null=True)
    is_refrigerated = serializers.BooleanField(required=False, default=False)
    current_load_weight = serializers.FloatField(read_only=True)
    current_load_volume = serializers.FloatField(read_only=True)

    # Fleet Mgmt Fields
    purchase_date = serializers.DateField(required=False, allow_null=True)
    current_mileage = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    next_service_mileage = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)
    next_service_date = serializers.DateField(required=False, allow_null=True)
    fuel_consumption_rate = serializers.DecimalField(max_digits=5, decimal_places=2, required=False)
    
    maintenance_logs = MaintenanceLogSerializer(many=True, read_only=True)
    fuel_expenses = FuelExpenseSerializer(many=True, read_only=True)

    class Meta:
        model = Vehicle
        fields = ('id', 'plate_number', 'vehicle_type', 'make_model', 'manufacturer', 'year', 'capacity', 'volume', 'assignedDriver', 'driver_name', 'status', 'insurance_expiry', 'registration_expiry', 'is_refrigerated', 'current_load_weight', 'current_load_volume', 'purchase_date', 'current_mileage', 'next_service_mileage', 'next_service_date', 'fuel_consumption_rate', 'maintenance_logs', 'fuel_expenses')

    def get_assignedDriver(self, obj):
        active_assignment = obj.assignments.filter(status='active').first()
        if active_assignment and active_assignment.driver and hasattr(active_assignment.driver, 'employee'):
            return active_assignment.driver.employee.user.user_id
        return None

    def get_driver_name(self, obj):
        active_assignment = obj.assignments.filter(status='active').first()
        if active_assignment and active_assignment.driver and hasattr(active_assignment.driver, 'employee'):
            return active_assignment.driver.employee.full_name
        return "Unassigned"

    def validate_plate_number(self, value):
        import re
        # Regex: 2-3 uppercase letters + hyphen + 4 digits OR 8 digits
        if not (re.match(r'^[A-Z]{2,3}-\d{4}$', value) or re.match(r'^\d{8}$', value)):
            raise serializers.ValidationError("License plate must be 'AA-1234', 'AAA-1234', or 8 digits.")
        return value

    def validate_year(self, value):
        from datetime import date
        if value > date.today().year:
            raise serializers.ValidationError("Vehicle year cannot be in the future.")
        return value

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance

class VehicleAssignmentSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source='assignment_id', read_only=True)
    driver_username = serializers.SerializerMethodField()

    class Meta:
        model = VehicleAssignment
        fields = ('id', 'driver_username', 'vehicle', 'assignment_start_date', 'assignment_end_date', 'status', 'rating')
        read_only_fields = ('assignment_start_date', 'assignment_end_date', 'status')

    def get_driver_username(self, obj):
        try:
            return obj.driver.employee.user.username
        except:
            return "Unknown"

class OrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = '__all__'

    def validate_weight_kg(self, value):
        if value is not None and float(value) <= 0:
            raise serializers.ValidationError("Weight must be a positive number.")
        return value

    def validate_volume_m3(self, value):
        if value is not None and float(value) <= 0:
            raise serializers.ValidationError("Volume must be a positive number.")
        return value

    def validate_quantity(self, value):
        if value is not None and int(value) < 1:
            raise serializers.ValidationError("Quantity must be at least 1.")
        return value

    def validate(self, data):
        """Cross-field validation for order integrity."""
        # Ensure addresses are provided on creation
        if self.instance is None:  # Creating new order
            if not data.get('pickup_address', '').strip():
                raise serializers.ValidationError({"pickup_address": "Pickup address is required."})
            if not data.get('delivery_address', '').strip():
                raise serializers.ValidationError({"delivery_address": "Delivery address is required."})
        return data

    def create(self, validated_data):
        from .utils.geocoding import geocode_address
        
        # 1. Geocode Pickup address
        pickup_addr = validated_data.get('pickup_address')
        if pickup_addr:
            lat, lng = geocode_address(pickup_addr)
            validated_data['pickup_lat'] = lat
            validated_data['pickup_lng'] = lng
            
        # 2. Geocode Delivery address
        delivery_addr = validated_data.get('delivery_address')
        if delivery_addr:
            lat, lng = geocode_address(delivery_addr)
            validated_data['delivery_lat'] = lat
            validated_data['delivery_lng'] = lng
            
        return super().create(validated_data)

class ShipmentOrderSerializer(serializers.ModelSerializer):
    order_details = OrderSerializer(source='order', read_only=True)
    class Meta:
        model = ShipmentOrder
        fields = ('order', 'order_details')

class ShipmentSerializer(serializers.ModelSerializer):
    orders = ShipmentOrderSerializer(source='order_mappings', many=True, read_only=True)
    vehicle_plate = serializers.CharField(source='vehicle.plate_number', read_only=True)
    driver_name = serializers.CharField(source='driver.employee.full_name', read_only=True)
    vehicle_details = VehicleSerializer(source='vehicle', read_only=True)

    class Meta:
        model = Shipment
        fields = ('shipment_id', 'vehicle', 'vehicle_details', 'vehicle_plate', 'driver', 'driver_name', 'total_weight', 'total_volume', 'shipment_type', 'requires_refrigeration', 'status', 'created_at', 'deployed_at', 'orders')

class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = '__all__'

class OrderExceptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderException
        fields = '__all__'

class OrderStatusLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderStatusLog
        fields = '__all__'

class ProofOfDeliverySerializer(serializers.ModelSerializer):
    class Meta:
        model = ProofOfDelivery
        fields = '__all__'
