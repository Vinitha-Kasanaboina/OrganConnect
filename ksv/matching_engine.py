import math
from typing import List, Dict, Any
from .models import Donor, Receiver

def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two coordinates in kilometers using Haversine formula."""
    if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
        return float('inf')
    
    R = 6371.0  # Earth's radius in km
    
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    
    a = (math.sin(delta_phi / 2) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    return R * c

def is_blood_compatible(donor_bg: str, receiver_bg: str) -> bool:
    """
    Check if donor blood group is compatible with receiver blood group.
    ABO & Rh factor rules:
    - O- can donate to all
    - O+ can donate to O+, A+, B+, AB+
    - A- can donate to A-, A+, AB-, AB+
    - A+ can donate to A+, AB+
    - B- can donate to B-, B+, AB-, AB+
    - B+ can donate to B+, AB+
    - AB- can donate to AB-, AB+
    - AB+ can donate only to AB+
    """
    db = donor_bg.strip().upper()
    rb = receiver_bg.strip().upper()
    
    # Extract ABO and Rh factor
    d_abo = db[:-1]
    d_rh = db[-1]
    r_abo = rb[:-1]
    r_rh = rb[-1]
    
    # Check Rh compatibility: Rh- can donate to both, Rh+ can only donate to Rh+
    if d_rh == '+' and r_rh == '-':
        return False
        
    # Check ABO compatibility
    if d_abo == 'O':
        return True
    elif d_abo == 'A':
        return r_abo in ['A', 'AB']
    elif d_abo == 'B':
        return r_abo in ['B', 'AB']
    elif d_abo == 'AB':
        return r_abo == 'AB'
        
    return False

def parse_hla_alleles(hla_str: str) -> set:
    """Parse comma/space/semicolon separated HLA allele list."""
    if not hla_str:
        return set()
    cleaned = hla_str.replace(';', ',').replace(' ', ',')
    parts = [p.strip().upper() for p in cleaned.split(',') if p.strip()]
    return set(parts)

def calculate_match_score(donor: Donor, receiver: Receiver) -> Dict[str, Any]:
    """
    Calculate compatibility score (0-100) between a donor and receiver.
    Returns score and list of reasons.
    """
    reasons = []
    
    # 1. Organ Match (Must match exactly)
    if donor.organ != receiver.organ:
        return {'score': 0, 'compatible': False, 'reasons': ['Organ mismatch']}
        
    # 2. Blood compatibility
    if not is_blood_compatible(donor.blood_group, receiver.blood_group):
        return {'score': 0, 'compatible': False, 'reasons': [f'Blood group incompatible ({donor.blood_group} to {receiver.blood_group})']}
        
    score = 40.0  # Base compatibility score for organ + blood match
    reasons.append(f"Organ and blood group compatibility established (+40 pts)")
    
    # 3. HLA compatibility (max 20 pts)
    d_hla = parse_hla_alleles(donor.hla_typing)
    r_hla = parse_hla_alleles(receiver.hla_typing)
    
    if d_hla and r_hla:
        overlap = d_hla.intersection(r_hla)
        union = d_hla.union(r_hla)
        jaccard = len(overlap) / len(union) if union else 0.0
        hla_score = round(jaccard * 20.0, 1)
        if hla_score > 0:
            score += hla_score
            reasons.append(f"HLA tissue compatibility matches: {list(overlap)} (+{hla_score} pts)")
        else:
            reasons.append("No common HLA alleles identified (+0 pts)")
    else:
        reasons.append("HLA typing data missing or incomplete for one or both parties (+0 pts)")
        
    # 4. Weight compatibility (max 10 pts)
    # Ideally donor's weight should be within 20% of receiver's weight to prevent organ sizing issues
    weight_diff = abs(donor.weight - receiver.weight) / receiver.weight
    if weight_diff <= 0.1:
        score += 10
        reasons.append("Excellent organ size matching, weight within 10% (+10 pts)")
    elif weight_diff <= 0.2:
        score += 5
        reasons.append("Acceptable organ size matching, weight within 20% (+5 pts)")
    else:
        reasons.append("Sub-optimal size matching, weight difference exceeds 20% (+0 pts)")
        
    # 5. Medical Urgency (max 15 pts)
    urgency = receiver.medical_urgency
    if urgency == 'CRITICAL':
        score += 15
        reasons.append("Receiver medical urgency is CRITICAL (+15 pts)")
    elif urgency == 'HIGH':
        score += 10
        reasons.append("Receiver medical urgency is HIGH (+10 pts)")
    elif urgency == 'MEDIUM':
        score += 5
        reasons.append("Receiver medical urgency is MEDIUM (+5 pts)")
    else:
        reasons.append("Receiver medical urgency is LOW (+0 pts)")
        
    # 6. Geographic Proximity (max 15 pts)
    # Check Coordinates first
    donor_prof = getattr(donor.user, 'profile', None) if donor.user else None
    receiver_prof = getattr(receiver.user, 'profile', None) if receiver.user else None
    
    lat1, lon1 = (donor_prof.latitude, donor_prof.longitude) if donor_prof else (None, None)
    lat2, lon2 = (receiver_prof.latitude, receiver_prof.longitude) if receiver_prof else (None, None)
    
    geo_pts = 0
    if lat1 is not None and lon1 is not None and lat2 is not None and lon2 is not None:
        dist = calculate_distance(lat1, lon1, lat2, lon2)
        if dist <= 50.0:
            geo_pts = 15
            reasons.append(f"Geographic proximity is excellent: {dist:.1f} km apart (+15 pts)")
        elif dist <= 200.0:
            geo_pts = 10
            reasons.append(f"Geographic proximity is good: {dist:.1f} km apart (+10 pts)")
        elif dist <= 500.0:
            geo_pts = 5
            reasons.append(f"Geographic proximity is moderate: {dist:.1f} km apart (+5 pts)")
        else:
            reasons.append(f"Geographic proximity is far: {dist:.1f} km apart (+0 pts)")
    else:
        # Fallback to regional state/city checks
        d_city = donor_prof.city if donor_prof else ""
        r_city = receiver_prof.city if receiver_prof else ""
        d_state = donor_prof.state if donor_prof else ""
        r_state = receiver_prof.state if receiver_prof else ""
        
        if d_city and r_city and d_city.strip().lower() == r_city.strip().lower():
            geo_pts = 12
            reasons.append(f"Donor and Receiver are located in the same city: {d_city} (+12 pts)")
        elif d_state and r_state and d_state.strip().lower() == r_state.strip().lower():
            geo_pts = 8
            reasons.append(f"Donor and Receiver are located in the same state: {d_state} (+8 pts)")
        else:
            reasons.append("Geographic location data not available or mismatching state (+0 pts)")
            
    score += geo_pts
    
    return {
        'score': round(score, 1),
        'compatible': True,
        'reasons': reasons
    }

def find_matches_for_receiver(receiver: Receiver) -> List[Dict[str, Any]]:
    """Find all compatible approved/verified donors for a receiver, sorted by compatibility score."""
    if receiver.status not in ['APPROVED', 'VERIFIED']:
        return []
        
    candidates = Donor.objects.filter(status__in=['APPROVED', 'VERIFIED'], organ=receiver.organ)
    matches = []
    
    for donor in candidates:
        match_info = calculate_match_score(donor, receiver)
        if match_info['compatible']:
            matches.append({
                'donor': donor,
                'receiver': receiver,
                'score': match_info['score'],
                'reasons': match_info['reasons']
            })
            
    # Sort matches descending by score
    matches.sort(key=lambda x: x['score'], reverse=True)
    return matches

def run_global_matching_engine() -> List[Dict[str, Any]]:
    """Scan all unmatched, approved/verified donors and receivers and generate recommended matching pairings."""
    receivers = Receiver.objects.filter(status__in=['APPROVED', 'VERIFIED'])
    all_recommendations = []
    
    for receiver in receivers:
        matches = find_matches_for_receiver(receiver)
        all_recommendations.extend(matches)
        
    # Sort all globally recommended matches by score
    all_recommendations.sort(key=lambda x: x['score'], reverse=True)
    return all_recommendations


def get_automatic_matched_pairs() -> List[Dict[str, Any]]:
    """
    Automatically compare all active donor and receiver records for Organ Type & Blood Group compatibility.
    Returns structured matching pairs with Donor Name, Receiver Name, Organ Type, Blood Group, Status, and Hospital.
    """
    from .models import Donor, Receiver
    
    # Fetch all active donors and receivers (excluding rejected records)
    donors = Donor.objects.exclude(status='REJECTED')
    receivers = Receiver.objects.exclude(status='REJECTED')
    
    matched_pairs = []
    seen_pairs = set()
    
    for receiver in receivers:
        for donor in donors:
            pair_key = (donor.id, receiver.id)
            if pair_key in seen_pairs:
                continue
                
            # 1. Organ Type match check
            if donor.organ != receiver.organ:
                continue
                
            # 2. Blood Group compatibility check
            if not is_blood_compatible(donor.blood_group, receiver.blood_group):
                continue
                
            # Compute compatibility score and rationale
            match_info = calculate_match_score(donor, receiver)
            
            # Determine hospital assigned
            assigned_hospital = "Unassigned"
            if donor.hospital:
                assigned_hospital = donor.hospital.name
            elif receiver.hospital:
                assigned_hospital = receiver.hospital.name
                
            matched_pairs.append({
                'donor': donor,
                'donor_name': donor.name,
                'donor_id': donor.anonymous_id,
                'donor_blood_group': donor.blood_group,
                'receiver': receiver,
                'receiver_name': receiver.name,
                'receiver_id': receiver.anonymous_id,
                'receiver_blood_group': receiver.blood_group,
                'organ_type': donor.organ,
                'blood_group': f"{donor.blood_group} → {receiver.blood_group}",
                'status': 'Matched',
                'hospital': assigned_hospital,
                'donor_hospital': donor.hospital,
                'receiver_hospital': receiver.hospital,
                'score': match_info['score'],
                'reasons': match_info['reasons']
            })
            seen_pairs.add(pair_key)
            
    # Sort pairs by compatibility score descending
    matched_pairs.sort(key=lambda x: x['score'], reverse=True)
    return matched_pairs


def sync_automatic_matches():
    """
    Automatically creates or updates MatchRecord entries for newly matched donor-receiver pairs in DB.
    Called when a new donor or receiver is added or updated.
    """
    from .models import MatchRecord
    pairs = get_automatic_matched_pairs()
    for item in pairs:
        MatchRecord.objects.get_or_create(
            donor=item['donor'],
            receiver=item['receiver'],
            defaults={
                'compatibility_score': item['score'],
                'status': 'PROPOSED',
                'matching_rationale': "; ".join(item['reasons'])
            }
        )


