"""
Entitlement State Machine - Phase 3

Manages state transitions for entitlements with business rule enforcement.

State Flow:
    ACTIVE (claimed)
         ↓
    PENDING_CONFIRMATION (QR validated)
         ↓
    CONFIRMED (confirmed by merchant)
    
    Any state → EXPIRED (time-based)
"""

from typing import Dict, Set, Optional
from datetime import datetime
from app.shared.enums import EntitlementState


class EntitlementStateMachine:
    """
    State machine for entitlement lifecycle
    
    Enforces valid state transitions and business rules
    """
    
    # Define valid state transitions
    VALID_TRANSITIONS: Dict[EntitlementState, Set[EntitlementState]] = {
        EntitlementState.ACTIVE: {
            EntitlementState.PENDING_CONFIRMATION,
            EntitlementState.EXPIRED
        },
        EntitlementState.PENDING_CONFIRMATION: {
            EntitlementState.CONFIRMED,
            EntitlementState.ACTIVE,  # Cancel validation
            EntitlementState.EXPIRED
        },
        EntitlementState.CONFIRMED: set(),   # Terminal state
        EntitlementState.CANCELLED: set(),   # Terminal state
        EntitlementState.EXPIRED: set()      # Terminal state
    }

    
    def __init__(self):
        """Initialize state machine"""
        pass
    
    def can_transition(self, from_state: EntitlementState, to_state: EntitlementState) -> bool:
        """
        Check if state transition is valid
        
        Args:
            from_state: Current state
            to_state: Desired state
            
        Returns:
            True if transition is allowed
        """
        if from_state not in self.VALID_TRANSITIONS:
            return False
        
        return to_state in self.VALID_TRANSITIONS[from_state]
    
    def validate_transition(
        self,
        from_state: EntitlementState,
        to_state: EntitlementState,
        metadata: Optional[dict] = None
    ) -> tuple[bool, Optional[str]]:
        """
        Validate state transition with business rules
        
        Args:
            from_state: Current state
            to_state: New state
            metadata: Optional transition metadata (e.g., timestamps)
            
        Returns:
            (is_valid, error_message)
        """
        # Check if transition is allowed
        if not self.can_transition(from_state, to_state):
            return False, f"Invalid transition from {from_state.value} to {to_state.value}"
        
        return True, None
    
    def get_allowed_transitions(self, current_state: EntitlementState) -> Set[EntitlementState]:
        """
        Get allowed transitions from current state
        
        Args:
            current_state: Current state
            
        Returns:
            Set of allowed next states
        """
        return self.VALID_TRANSITIONS.get(current_state, set())
    
    def is_terminal_state(self, state: EntitlementState) -> bool:
        """
        Check if state is terminal (no further transitions)
        
        Args:
            state: State to check
            
        Returns:
            True if terminal state
        """
        return len(self.VALID_TRANSITIONS.get(state, set())) == 0
    
    def can_generate_qr(self, state: EntitlementState, expires_at: datetime) -> tuple[bool, Optional[str]]:
        """
        Check if QR code can be generated for entitlement
        
        Business rules:
        - Must be in ACTIVE state
        - Must not be expired
        
        Args:
            state: Current entitlement state
            expires_at: Entitlement expiry timestamp
            
        Returns:
            (can_generate, reason)
        """
        if state != EntitlementState.ACTIVE:
            return False, f"Cannot generate QR for entitlement in {state.value} state"
        
        if datetime.now(expires_at.tzinfo) >= expires_at:
            return False, "Entitlement has expired"
        
        return True, None
    
    def can_validate(self, state: EntitlementState) -> tuple[bool, Optional[str]]:
        """
        Check if entitlement can be validated (merchant scan)
        
        Business rules:
        - Must be in ACTIVE state
        
        Args:
            state: Current entitlement state
            
        Returns:
            (can_validate, reason)
        """
        if state != EntitlementState.ACTIVE:
            return False, f"Cannot validate entitlement in {state.value} state"
        
        return True, None
    
    def can_confirm(self, state: EntitlementState) -> tuple[bool, Optional[str]]:
        """
        Check if redemption can be confirmed
        
        Business rules:
        - Must be in PENDING_CONFIRMATION state
        
        Args:
            state: Current entitlement state
            
        Returns:
            (can_confirm, reason)
        """
        if state != EntitlementState.PENDING_CONFIRMATION:
            return False, f"Cannot confirm redemption for entitlement in {state.value} state"
        
        return True, None

# Global state machine instance
state_machine = EntitlementStateMachine()
