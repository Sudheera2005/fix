import os
import random
from decimal import Decimal
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction

# Import all models to ensure full cleanup and seeding
from api.models import (
    Role, CustomUser, Employee, Customer, VehicleAssignment, 
    Order, Shipment, ShipmentOrder, GPSPersistence, 
    OrderStatusLog, OrderException, ProofOfDelivery, AuditLog
)
from procurement.models import (
    Supplier as ProcurementSupplier, PurchaseOrder, POLineItem, 
    SupplierRun, RunPurchaseOrder, GoodsReceiptLine, InboundException as ProcInboundException
)
from warehouses.models import Warehouse, StockTransfer
from drivers.models import Driver as DriverProfile, TripLog
from vehicles.models import Vehicle, MaintenanceLog, FuelExpense
from inbound.models import (
    Supplier as InboundSupplier, SupplierDeliveryManifest, ManifestLineItem, 
    InboundCollectionAssignment, CollectedLineItem, InboundException as InboundExc
)

class Command(BaseCommand):
    help = 'Cleans the database except specific users, then seeds 6 months of historical data.'

    def handle(self, *args, **kwargs):
        self.stdout.write("Starting dedicated Database Seeder...")
        
        with transaction.atomic():
            self.cleanup_database()
            self.seed_base_entities()
            self.seed_historical_data()
            self.seed_demonstration_data()
        
        self.stdout.write(self.style.SUCCESS('Successfully seeded historical and demonstration data!'))

    def cleanup_database(self):
        self.stdout.write("Phase 1: Safe Database Cleanup")
        preserved_usernames = ['superadmin', 'manager', 'dispatcherz']
        
        # Explicit deletion of operations
        self.stdout.write("Deleting operational data...")
        ProofOfDelivery.objects.all().delete()
        OrderException.objects.all().delete()
        OrderStatusLog.objects.all().delete()
        GPSPersistence.objects.all().delete()
        ShipmentOrder.objects.all().delete()
        Shipment.objects.all().delete()
        VehicleAssignment.objects.all().delete()
        Order.objects.all().delete()
        
        InboundExc.objects.all().delete()
        CollectedLineItem.objects.all().delete()
        InboundCollectionAssignment.objects.all().delete()
        ManifestLineItem.objects.all().delete()
        SupplierDeliveryManifest.objects.all().delete()
        InboundSupplier.objects.all().delete()

        ProcInboundException.objects.all().delete()
        GoodsReceiptLine.objects.all().delete()
        RunPurchaseOrder.objects.all().delete()
        SupplierRun.objects.all().delete()
        POLineItem.objects.all().delete()
        PurchaseOrder.objects.all().delete()
        ProcurementSupplier.objects.all().delete()

        StockTransfer.objects.all().delete()
        Warehouse.objects.all().delete()

        MaintenanceLog.objects.all().delete()
        FuelExpense.objects.all().delete()
        TripLog.objects.all().delete()
        Vehicle.objects.all().delete()

        DriverProfile.objects.all().delete()
        Customer.objects.all().delete()
        Employee.objects.all().delete()
        AuditLog.objects.all().delete()

        # Users and Roles
        CustomUser.objects.exclude(username__in=preserved_usernames).delete()
        
        # Ensure preserved users exist
        role_admin, _ = Role.objects.get_or_create(role_name='Admin')
        role_manager, _ = Role.objects.get_or_create(role_name='Manager')
        role_dispatcher, _ = Role.objects.get_or_create(role_name='Dispatcher')
        
        users_to_create = [
            ('superadmin', 'admin@example.com', role_admin),
            ('manager', 'manager@example.com', role_manager),
            ('dispatcherz', 'dispatcherz@example.com', role_dispatcher)
        ]
        
        for username, email, role in users_to_create:
            if not CustomUser.objects.filter(username=username).exists():
                CustomUser.objects.create_user(username=username, email=email, password='password123', role=role)
        
        self.stdout.write("Database cleaned up successfully.")

    def seed_base_entities(self):
        self.stdout.write("Phase 2: Base Entity Seeding")
        
        # Warehouses
        self.warehouses = []
        for i in range(1, 4):
            wh = Warehouse.objects.create(
                name=f"Warehouse {i}",
                address=f"{100*i} Main St, City {i}",
                lat=Decimal(f"34.05{i}000"),
                lng=Decimal(f"-118.24{i}000")
            )
            self.warehouses.append(wh)
            
        # Vehicles
        self.vehicles = []
        for i in range(1, 11):
            v = Vehicle.objects.create(
                plate_number=f"TRK-{i*100}",
                vehicle_type='truck' if i % 2 == 0 else 'van',
                manufacturer='Ford' if i % 2 == 0 else 'Volvo',
                capacity_kg=Decimal(random.randint(1000, 10000)),
                capacity_volume=Decimal(random.randint(10, 50)),
                is_refrigerated=(i % 3 == 0),
                status='available'
            )
            self.vehicles.append(v)
            
        # Roles for Drivers/Customers
        role_driver, _ = Role.objects.get_or_create(role_name='Driver')
        role_customer, _ = Role.objects.get_or_create(role_name='Customer')
        
        # Drivers
        self.drivers = []
        for i in range(1, 11):
            u = CustomUser.objects.create_user(
                username=f"driver_{i}",
                email=f"driver{i}@example.com",
                password="password123",
                role=role_driver
            )
            emp = Employee.objects.create(
                user=u,
                full_name=f"Driver Name {i}",
                national_id=f"NID-{i*123}",
                contact_number=f"555-010{i}",
                address=f"Driver Home {i}",
                date_of_birth=timezone.now().date() - timedelta(days=365*30)
            )
            drv = DriverProfile.objects.create(
                employee=emp,
                license_number=f"LIC-{i*999}",
                license_expiry_date=timezone.now().date() + timedelta(days=365*2),
                experience_years=random.randint(1, 10),
                status='available'
            )
            self.drivers.append(drv)
            
        # Customers
        self.customers = []
        for i in range(1, 6):
            u = CustomUser.objects.create_user(
                username=f"customer_{i}",
                email=f"customer{i}@example.com",
                password="password123",
                role=role_customer
            )
            cust = Customer.objects.create(
                user=u,
                business_name=f"Customer Business {i}",
                email=f"customer{i}@example.com",
                phone_number=f"555-020{i}",
                address=f"Customer Addr {i}",
                latitude=Decimal(f"34.06{i}000"),
                longitude=Decimal(f"-118.25{i}000")
            )
            self.customers.append(cust)

    def seed_historical_data(self):
        self.stdout.write("Phase 3: 6-Month Historical Data Generation")
        today = timezone.now()
        
        # Loop over 180 days
        for day_offset in range(180, 0, -1):
            current_date = today - timedelta(days=day_offset)
            
            # Generate 2-5 orders per day
            for _ in range(random.randint(2, 5)):
                wh = random.choice(self.warehouses)
                drv = random.choice(self.drivers)
                veh = random.choice(self.vehicles)
                
                # Order
                order = Order.objects.create(
                    shipment_type=random.choice(['package', 'pallet']),
                    quantity=random.randint(1, 10),
                    weight_kg=Decimal(random.randint(10, 500)),
                    volume_m3=Decimal(random.randint(1, 10)),
                    pickup_address=wh.address,
                    delivery_address=random.choice(self.customers).address,
                    warehouse_id=wh.id,
                    warehouse_name=wh.name,
                    warehouse_address=wh.address,
                    assigned_vehicle=veh,
                    assigned_driver=drv,
                    status='delivered', # Historical is delivered
                    created_at=current_date,
                    updated_at=current_date + timedelta(hours=8)
                )
                
                # Force override created_at
                Order.objects.filter(pk=order.pk).update(created_at=current_date, updated_at=current_date + timedelta(hours=8))
                
                # Status Logs to mimic lifecycle
                OrderStatusLog.objects.create(order=order, from_status='pending', to_status='assigned', changed_at=current_date + timedelta(hours=1), source='system')
                OrderStatusLog.objects.create(order=order, from_status='assigned', to_status='in_transit', changed_at=current_date + timedelta(hours=2), source='driver_scan')
                OrderStatusLog.objects.create(order=order, from_status='in_transit', to_status='delivered', changed_at=current_date + timedelta(hours=8), source='driver_scan')
                
                # Overwrite timestamps of Status Logs
                OrderStatusLog.objects.filter(order=order, to_status='assigned').update(changed_at=current_date + timedelta(hours=1))
                OrderStatusLog.objects.filter(order=order, to_status='in_transit').update(changed_at=current_date + timedelta(hours=2))
                OrderStatusLog.objects.filter(order=order, to_status='delivered').update(changed_at=current_date + timedelta(hours=8))
                
                # Proof Of Delivery
                ProofOfDelivery.objects.create(
                    order=order,
                    recipient_name="John Doe",
                    timestamp=current_date + timedelta(hours=8)
                )
                ProofOfDelivery.objects.filter(order=order).update(timestamp=current_date + timedelta(hours=8))

                # Occasional Exception
                if random.random() < 0.1:
                    exc = OrderException.objects.create(
                        order=order,
                        exception_type=random.choice(['traffic_delay', 'damaged']),
                        driver=drv,
                        location_lat=Decimal("34.05"),
                        location_lng=Decimal("-118.25"),
                        reported_at=current_date + timedelta(hours=4)
                    )
                    OrderException.objects.filter(pk=exc.pk).update(reported_at=current_date + timedelta(hours=4))

            # Trip Logs & Fuel Expenses for some vehicles on this day
            for v in random.sample(self.vehicles, k=3):
                d = random.choice(self.drivers)
                TripLog.objects.create(
                    driver=d,
                    vehicle=v,
                    start_time=current_date + timedelta(hours=8),
                    end_time=current_date + timedelta(hours=16),
                    start_mileage=Decimal(random.randint(10000, 50000)),
                    end_mileage=Decimal(random.randint(50100, 60000)),
                    fuel_consumed=Decimal(random.randint(10, 50))
                )
                if random.random() < 0.2:
                    FuelExpense.objects.create(
                        vehicle=v,
                        date=current_date.date(),
                        liters=Decimal(random.randint(20, 100)),
                        cost_per_liter=Decimal("1.50"),
                        total_cost=Decimal("75.00"),
                        mileage_at_refill=Decimal(random.randint(10000, 50000))
                    )

    def seed_demonstration_data(self):
        self.stdout.write("Phase 4: Current Demonstration Data")
        today = timezone.now()
        
        # Create some Active Orders (pending, assigned, in_transit)
        for _ in range(5):
            wh = random.choice(self.warehouses)
            order = Order.objects.create(
                shipment_type='package',
                quantity=random.randint(1, 5),
                weight_kg=Decimal(random.randint(10, 100)),
                volume_m3=Decimal(random.randint(1, 5)),
                pickup_address=wh.address,
                delivery_address=random.choice(self.customers).address,
                warehouse_id=wh.id,
                warehouse_name=wh.name,
                warehouse_address=wh.address,
                status='pending'
            )
        
        for _ in range(3):
            wh = random.choice(self.warehouses)
            drv = random.choice(self.drivers)
            veh = random.choice(self.vehicles)
            order = Order.objects.create(
                shipment_type='pallet',
                quantity=random.randint(1, 5),
                weight_kg=Decimal(random.randint(100, 500)),
                volume_m3=Decimal(random.randint(2, 8)),
                pickup_address=wh.address,
                delivery_address=random.choice(self.customers).address,
                warehouse_id=wh.id,
                warehouse_name=wh.name,
                warehouse_address=wh.address,
                assigned_vehicle=veh,
                assigned_driver=drv,
                status='in_transit'
            )
            OrderStatusLog.objects.create(order=order, from_status='pending', to_status='in_transit', source='system')
            VehicleAssignment.objects.create(
                vehicle=veh,
                driver=drv,
                status='active',
                assignment_start_date=today - timedelta(hours=2)
            )

        # Some delayed orders
        for _ in range(2):
            wh = random.choice(self.warehouses)
            drv = random.choice(self.drivers)
            veh = random.choice(self.vehicles)
            order = Order.objects.create(
                shipment_type='package',
                quantity=1,
                weight_kg=Decimal(10),
                volume_m3=Decimal(1),
                pickup_address=wh.address,
                delivery_address=random.choice(self.customers).address,
                warehouse_id=wh.id,
                warehouse_name=wh.name,
                warehouse_address=wh.address,
                assigned_vehicle=veh,
                assigned_driver=drv,
                status='in_transit'
            )
            OrderException.objects.create(
                order=order,
                exception_type='traffic_delay',
                driver=drv,
                location_lat=Decimal("34.05"),
                location_lng=Decimal("-118.25"),
                notes="Stuck in heavy traffic on main highway."
            )

        # Current stock transfers
        wh1, wh2 = random.sample(self.warehouses, 2)
        StockTransfer.objects.create(
            source_warehouse=wh1,
            destination_warehouse=wh2,
            item_name="Demonstration Item",
            quantity=100,
            status='in_transit'
        )

        self.stdout.write("Demonstration data generated.")

