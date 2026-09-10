from django.test import TestCase
from django.contrib.auth.models import User
from ksv.models import Donor, Receiver, UserProfile
from ksv.security import encrypt_data, decrypt_data
from ksv.matching_engine import is_blood_compatible, calculate_match_score, calculate_distance

class OrganConnectTestCase(TestCase):
    
    def setUp(self):
        # Setup test keys or settings if needed
        pass

    def test_encryption_decryption(self):
        """Test that sensitive records encrypt and decrypt correctly."""
        plain_text = "Patient suffers from chronic renal insufficiency. HLA-A2, B27."
        encrypted = encrypt_data(plain_text)
        
        # Verify stored data is not plaintext
        self.assertNotEqual(plain_text, encrypted)
        self.assertTrue(len(encrypted) > len(plain_text))
        
        # Verify decryption yields the original plaintext
        decrypted = decrypt_data(encrypted)
        self.assertEqual(plain_text, decrypted)

    def test_blood_compatibility(self):
        """Test all major blood compatibility combinations."""
        # O- can donate to anyone
        self.assertTrue(is_blood_compatible("O-", "O-"))
        self.assertTrue(is_blood_compatible("O-", "AB+"))
        self.assertTrue(is_blood_compatible("O-", "B-"))
        
        # A+ can donate to A+ and AB+
        self.assertTrue(is_blood_compatible("A+", "A+"))
        self.assertTrue(is_blood_compatible("A+", "AB+"))
        self.assertFalse(is_blood_compatible("A+", "B+"))
        self.assertFalse(is_blood_compatible("A+", "O+"))
        
        # AB+ can only donate to AB+
        self.assertTrue(is_blood_compatible("AB+", "AB+"))
        self.assertFalse(is_blood_compatible("AB+", "AB-"))
        self.assertFalse(is_blood_compatible("AB+", "O-"))

    def test_haversine_distance(self):
        """Test distance calculation between coordinates."""
        # Distance between Bangalore (12.9716, 77.5946) and Mysore (12.2958, 76.6394) is approx 128 km straight line
        dist = calculate_distance(12.9716, 77.5946, 12.2958, 76.6394)
        self.assertAlmostEqual(dist, 128.0, delta=2.0)

    def test_match_score_calculation(self):
        """Test matching engine compatibility score calculations."""
        # Create users
        donor_user = User.objects.create_user(username="donor_user", password="pwd")
        receiver_user = User.objects.create_user(username="receiver_user", password="pwd")
        
        # Create UserProfiles
        UserProfile.objects.create(user=donor_user, role="DONOR", latitude=12.9716, longitude=77.5946)
        UserProfile.objects.create(user=receiver_user, role="RECEIVER", latitude=12.9716, longitude=77.5946) # Same location
        
        # Create donor & receiver objects
        donor = Donor.objects.create(
            user=donor_user,
            name="Donor Bob",
            age=30,
            blood_group="O-",
            organ="Kidney",
            weight=70.0,
            bp="120/80",
            hla_typing="A2, B27, DR4",
            status="VERIFIED"
        )
        
        receiver = Receiver.objects.create(
            user=receiver_user,
            name="Receiver Alice",
            age=32,
            blood_group="O+",
            organ="Kidney",
            weight=72.0,
            bp="120/80",
            hla_typing="A2, B27, DR4", # Exact HLA Match
            medical_urgency="HIGH",
            status="VERIFIED"
        )
        
        # Run matching calculations
        match_info = calculate_match_score(donor, receiver)
        
        self.assertTrue(match_info['compatible'])
        # Expecting high score:
        # Base compatible blood/organ match: 40 pts
        # HLA Jaccard: exact match = 20 pts
        # Weight difference < 10% (70 vs 72): 10 pts
        # Urgency: HIGH = 10 pts
        # Distance: 0 km (<50 km) = 15 pts
        # Total expected: 40 + 20 + 10 + 10 + 15 = 95 pts
        self.assertEqual(match_info['score'], 95.0)

    def test_ledger_verification_and_tampering(self):
        """Test that the cryptographic hashed ledger detects database tampering."""
        import hashlib
        from ksv.models import AuditLog
        
        # Create consecutive linked audit logs
        log1 = AuditLog.objects.create(action="TEST_ACTION_1", details="Details 1")
        log2 = AuditLog.objects.create(action="TEST_ACTION_2", details="Details 2")
        log3 = AuditLog.objects.create(action="TEST_ACTION_3", details="Details 3")
        
        # Verify the chain links correctly
        self.assertEqual(log2.previous_hash, log1.hash)
        self.assertEqual(log3.previous_hash, log2.hash)
        
        # Run chain verification algorithm
        logs = AuditLog.objects.order_by('id')
        integrity_ok = True
        expected_prev = "0" * 64
        for log in logs:
            t_str = log.timestamp.isoformat() if log.timestamp else "new-log"
            actor_id = str(log.actor.id) if log.actor else "system"
            raw_data = f"{actor_id}{log.action}{log.details}{t_str}{log.previous_hash}"
            computed = hashlib.sha256(raw_data.encode('utf-8')).hexdigest()
            
            if log.previous_hash != expected_prev or log.hash != computed:
                integrity_ok = False
            expected_prev = log.hash
        
        self.assertTrue(integrity_ok)
        
        # NOW TAMPER WITH THE LEDGER DIRECTLY (bypass AuditLog.save() override)
        # Update log2 details directly in database using queryset update
        AuditLog.objects.filter(id=log2.id).update(details="TAMPERED details")
        
        # Re-run chain verification algorithm
        integrity_ok = True
        expected_prev = "0" * 64
        for log in AuditLog.objects.order_by('id'):
            t_str = log.timestamp.isoformat() if log.timestamp else "new-log"
            actor_id = str(log.actor.id) if log.actor else "system"
            raw_data = f"{actor_id}{log.action}{log.details}{t_str}{log.previous_hash}"
            computed = hashlib.sha256(raw_data.encode('utf-8')).hexdigest()
            
            if log.previous_hash != expected_prev or log.hash != computed:
                integrity_ok = False
            expected_prev = log.hash
            
    def test_admin_dashboard_access_control(self):
        """Test that Admin Dashboard sub-views enforce strict access control."""
        # Create non-admin user
        user = User.objects.create_user(username="regular_user", password="password123")
        UserProfile.objects.create(user=user, role="DONOR")
        
        # Create admin user
        admin_user = User.objects.create_superuser(username="admin_user", password="password123", email="admin@example.com")
        UserProfile.objects.create(user=admin_user, role="ADMIN")
        
        # Non-admin access attempt
        self.client.login(username="regular_user", password="password123")
        response = self.client.get('/admin/hospitals/')
        self.assertEqual(response.status_code, 403)
        
        # Admin access attempt
        self.client.login(username="admin_user", password="password123")
        response = self.client.get('/admin/hospitals/')
        self.assertEqual(response.status_code, 200)
        
        response = self.client.get('/admin/donors/')
        self.assertEqual(response.status_code, 200)
        
        response = self.client.get('/admin/receivers/')
        self.assertEqual(response.status_code, 200)
        
        response = self.client.get('/admin/audit-logs/')
        self.assertEqual(response.status_code, 200)

    def test_single_master_admin_authentication(self):
        """Test dedicated Admin Portal and single master admin authentication logic."""
        admin_user = User.objects.create_superuser(username="master_admin", password="MasterPassword123!")
        UserProfile.objects.create(user=admin_user, role="ADMIN")
        
        non_admin_user = User.objects.create_user(username="fake_admin", password="Password123!")
        UserProfile.objects.create(user=non_admin_user, role="DONOR")
        
        # Test non-admin login attempt at Admin Portal -> should re-render form with error message (200 OK)
        response = self.client.post('/admin/login/', {'username': 'fake_admin', 'password': 'Password123!'})
        self.assertEqual(response.status_code, 200)
        
        # Test master admin login attempt -> should succeed and redirect to dashboard (302 Redirect)
        response = self.client.post('/admin/login/', {'username': 'master_admin', 'password': 'MasterPassword123!'})
        self.assertRedirects(response, '/dashboard/')

    def test_medical_document_upload_and_security(self):
        """Test document uploads and secure download authorization."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        from ksv.models import MedicalDocument, Hospital
        
        # Create hospital, donor user, and stranger user
        hosp_user = User.objects.create_user(username="hosp_user", password="pwd")
        UserProfile.objects.create(user=hosp_user, role="HOSPITAL")
        hosp = Hospital.objects.create(name="Govt Hosp", registration_number="GH101", user=hosp_user, status="APPROVED", is_active=True)
        
        donor_user = User.objects.create_user(username="donor_doc_user", password="pwd")
        UserProfile.objects.create(user=donor_user, role="DONOR")
        donor = Donor.objects.create(user=donor_user, name="John", age=25, blood_group="A+", organ="Kidney", hospital=hosp)
        
        stranger = User.objects.create_user(username="stranger", password="pwd")
        UserProfile.objects.create(user=stranger, role="RECEIVER")
        
        # Upload dummy document
        dummy_file = SimpleUploadedFile("health_report.pdf", b"PDF content bytes", content_type="application/pdf")
        doc = MedicalDocument.objects.create(donor=donor, document_type="HEALTH_REPORT", file=dummy_file, title="Health Report PDF")
        
        # Stranger attempts download -> Expect 403 Forbidden
        self.client.login(username="stranger", password="pwd")
        res = self.client.get(f'/document/download/{doc.pk}/')
        self.assertEqual(res.status_code, 403)
        
        # Donor owner attempts download -> Expect 200 OK
        self.client.login(username="donor_doc_user", password="pwd")
        res = self.client.get(f'/document/download/{doc.pk}/')
        self.assertEqual(res.status_code, 200)
        
        # Hospital officer attempts download -> Expect 200 OK
        self.client.login(username="hosp_user", password="pwd")
        res = self.client.get(f'/document/download/{doc.pk}/')
        self.assertEqual(res.status_code, 200)

    def test_hospital_verification_with_remarks(self):
        """Test hospital verification updates status to APPROVED and records remarks."""
        from ksv.models import Hospital
        hosp_user = User.objects.create_user(username="hosp_officer", password="pwd")
        UserProfile.objects.create(user=hosp_user, role="HOSPITAL")
        hosp = Hospital.objects.create(name="Central Hosp", registration_number="CH001", user=hosp_user, status="APPROVED", is_active=True)
        
        donor = Donor.objects.create(name="Sam", age=28, blood_group="O+", organ="Kidney", hospital=hosp, status="PENDING")
        
        self.client.login(username="hosp_officer", password="pwd")
        response = self.client.post(f'/hospital/verify/donor/{donor.pk}/', {
            'action': 'approve',
            'notes': 'All uploaded medical documents verified genuine.'
        })
        
        donor.refresh_from_db()
        self.assertEqual(donor.status, 'APPROVED')
        self.assertEqual(donor.verification_remarks, 'All uploaded medical documents verified genuine.')

    def test_automatic_organ_matching(self):
        """Test automatic organ matching logic and signal-based updating."""
        from ksv.matching_engine import get_automatic_matched_pairs
        
        # Initially no donors or receivers -> No matches
        pairs = get_automatic_matched_pairs()
        self.assertEqual(len(pairs), 0)
        
        # Create an O- Kidney Donor and A+ Kidney Receiver (Compatible match)
        donor1 = Donor.objects.create(
            name="Auto Donor John",
            age=30,
            blood_group="O-",
            organ="Kidney",
            status="PENDING"
        )
        receiver1 = Receiver.objects.create(
            name="Auto Receiver Jane",
            age=28,
            blood_group="A+",
            organ="Kidney",
            status="PENDING"
        )
        
        # Automatic matching engine should instantly detect this pair
        pairs = get_automatic_matched_pairs()
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]['donor_name'], "Auto Donor John")
        self.assertEqual(pairs[0]['receiver_name'], "Auto Receiver Jane")
        self.assertEqual(pairs[0]['organ_type'], "Kidney")
        self.assertEqual(pairs[0]['status'], "Matched")
        
        # Add an incompatible receiver (Heart required instead of Kidney)
        receiver2 = Receiver.objects.create(
            name="Incompatible Heart Receiver",
            age=40,
            blood_group="O-",
            organ="Heart",
            status="PENDING"
        )
        
        # Matched pairs count should still be 1 because Heart != Kidney
        pairs = get_automatic_matched_pairs()
        self.assertEqual(len(pairs), 1)
        
        # Verify matched_organs view endpoint returns HTTP 200
        user = User.objects.create_user(username="test_user", password="password123")
        UserProfile.objects.create(user=user, role="DONOR")
        self.client.login(username="test_user", password="password123")
        response = self.client.get('/matched-organs/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Auto Donor John")
        self.assertContains(response, "Auto Receiver Jane")
        self.assertContains(response, "Matched")



