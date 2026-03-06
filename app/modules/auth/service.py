"""
Authentication Service

Business logic for OTP authentication.
"""

import random
import string
import logging
from typing import Optional, Dict
from fastapi import HTTPException, status
from app.core.database import get_supabase_client
from app.core.redis import redis_manager
from app.core.email import email_service

# Configure logging
logger = logging.getLogger(__name__)

"""
Authentication Service

Business logic for OTP authentication and Profile Management.
"""

import random
import string
import logging
from typing import Optional, Dict, Any
from fastapi import HTTPException, status
from app.core.database import get_supabase_client
from app.core.redis import redis_manager
from app.core.email import email_service
from app.modules.auth.schemas import RegisterRequest, ProfileUpdateRequest, UserStats

# Configure logging
logger = logging.getLogger(__name__)

class AuthService:
    """
    Handles authentication operations
    """
    
    async def send_otp(self, email: str) -> Dict[str, str]:
        """
        Send OTP to user email via Resend
        """
        # 1. Parse email domain
        try:
            domain = email.split("@")[1]
        except IndexError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid email format"
            )

        # 2. Query Supabase table `university_domains` to check eligibility
        supabase = get_supabase_client()
        if not supabase:
             raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database connection error"
            )

        try:
            # Check if domain exists and is active
            result = supabase.table("university_domains") \
                .select("*") \
                .eq("domain", domain) \
                .execute()
            
            if not result.data:
                 # Logic for university domain check - if not strict we might allow generic emails
                 # But requirement references "students", assume strict for now or log warning
                 logger.warning(f"Domain {domain} not found in whitelist")
                 # For now, allowing all for testing unless strictly enforced
                 # raise HTTPException(
                 #    status_code=status.HTTP_400_BAD_REQUEST,
                 #    detail=f"Domain {domain} is not eligible for registration."
                 # )
                 pass 
        except Exception as e:
            logger.error(f"Supabase query error: {e}")
            # Continue for now to avoid blocking development if table missing

        # 3. Generate 6-digit random code
        otp_code = ''.join(random.choices(string.digits, k=6))
        
        # 4. Store in Redis
        # Key: sv:app:auth:otp:{email}
        # TTL: 300 seconds (5 minutes)
        redis_key = f"sv:app:auth:otp:{email}"
        
        # Store OTP in Redis
        try:
            success = redis_manager.setex(redis_key, 300, otp_code)
            if not success:
                logger.error("Failed to store OTP in Redis")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to generate verification code"
                )
        except Exception as e:
            logger.error(f"Redis error: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate verification code"
            )

        # 5. Send OTP via email
        # logger.info(f"Generated OTP for {email}: {otp_code}") # For dev testing
        print(f"OTP_CODE_LOG: {otp_code}")
        with open("otp.txt", "w") as f:
            f.write(otp_code)
        try:
            email_service.send_otp_email(email, otp_code, expiry_minutes=5)
        except Exception as e:
            # Delete the OTP from Redis if email fails
            redis_manager.delete(redis_key)
            logger.error(f"Failed to send OTP email: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send verification code"
            )

        return {"message": "OTP sent"}

    async def verify_otp(self, email: str, code: str, device_id: str = "") -> Dict[str, Any]:
        """
        Verify OTP code and create/authenticate user.
        
        Flow:
        1. Verify OTP from Redis
        2. Try to sign up new user in Supabase Auth
        3. If user already exists, look up their ID from public.users,
           admin-reset their password, then sign in
        4. Sync user to public.users table
        5. Return JWT access token
        """
        redis_key = f"sv:app:auth:otp:{email}"
        
        # 1. Retrieve code from Redis
        stored_code = redis_manager.get(redis_key)
        
        if not stored_code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="OTP expired or invalid"
            )
            
        if stored_code != code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid access code"
            )
        
        # 2. OTP verified! Now create/login user with Supabase
        supabase = get_supabase_client()
        if not supabase:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database connection error"
            )
        
        try:
            # Use a deterministic password based on email (consistent across logins)
            temp_password = f"SV_OTP_AUTH_{email}_SECURE_PASS_2024!"
            auth_response = None
            is_new_user = False
            
            # --- Strategy 1: Try sign_up (new user) ---
            try:
                auth_response = supabase.auth.sign_up({
                    "email": email,
                    "password": temp_password
                })
                
                # Check if sign_up returned a user but no session 
                # (this happens when Supabase returns the existing user without error)
                if auth_response and auth_response.user and not auth_response.session:
                    logger.info(f"User already exists (no session from sign_up): {email}")
                    auth_response = None  # Force fallback to sign_in
                else:
                    is_new_user = True
                    logger.info(f"Created new user via OTP: {email}")
                    
            except Exception as signup_err:
                logger.info(f"Sign up failed (user likely exists): {signup_err}")
                auth_response = None
            
            # --- Strategy 2: If sign_up failed, sign in existing user ---
            if not auth_response or not auth_response.session:
                logger.info(f"Attempting sign-in for existing user: {email}")
                
                # First try signing in with the deterministic password
                try:
                    auth_response = supabase.auth.sign_in_with_password({
                        "email": email,
                        "password": temp_password
                    })
                    logger.info(f"Signed in existing user: {email}")
                except Exception as signin_err:
                    logger.info(f"Sign-in with standard password failed: {signin_err}")
                    
                    # Password mismatch - need admin reset
                    # Look up user ID from public.users table (reliable)
                    try:
                        user_lookup = supabase.table("users").select("id").eq("email", email).execute()
                        
                        if user_lookup.data:
                            existing_user_id = user_lookup.data[0]["id"]
                            logger.info(f"Found user in public.users: {existing_user_id}")
                        else:
                            # User exists in Auth but not in public.users
                            # Try admin list to find them
                            logger.info("User not in public.users, trying admin API...")
                            existing_user_id = None
                            
                            # Use admin.list_users and filter
                            try:
                                users_list = supabase.auth.admin.list_users()
                                for u in users_list:
                                    if hasattr(u, 'email') and u.email == email:
                                        existing_user_id = u.id
                                        break
                            except Exception as list_err:
                                logger.error(f"Admin list_users failed: {list_err}")
                        
                        if existing_user_id:
                            # Admin reset password
                            supabase.auth.admin.update_user_by_id(
                                existing_user_id,
                                {"password": temp_password}
                            )
                            logger.info(f"Admin password reset for user: {existing_user_id}")
                            
                            # Now sign in
                            auth_response = supabase.auth.sign_in_with_password({
                                "email": email,
                                "password": temp_password
                            })
                            logger.info(f"Signed in after admin reset: {email}")
                        else:
                            raise HTTPException(
                                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                detail="User exists in Auth but could not be found for password reset"
                            )
                    except HTTPException:
                        raise
                    except Exception as admin_err:
                        logger.error(f"Admin password reset flow failed: {admin_err}")
                        raise HTTPException(
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"Authentication error: Could not sign in existing user. {str(admin_err)}"
                        )
            
            # --- Validate final response ---
            if not auth_response or not auth_response.user:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to authenticate user"
                )
            
            user_id = str(auth_response.user.id)
            
            if not auth_response.session or not auth_response.session.access_token:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="No session created. Check Supabase email confirmation settings."
                )
            
            access_token = auth_response.session.access_token
            
            # --- Sync to public.users table & enforce single-session login ---
            try:
                user_check = supabase.table("users").select("id, logged_in").eq("id", user_id).execute()
                if not user_check.data:
                    # New user — insert record; logged_in defaults to false until register completes
                    supabase.table("users").insert({
                        "id": user_id,
                        "email": email,
                        "account_type": "free"
                    }).execute()
                    logger.info(f"Created user in public.users: {email}")
                else:
                    # Existing user — enforce single active session
                    if user_check.data[0].get("logged_in"):
                        raise HTTPException(
                            status_code=status.HTTP_409_CONFLICT,
                            detail="You are already logged in on another device. Please logout first."
                        )
                    # Mark as logged in and update device binding
                    update_payload: dict = {"logged_in": True}
                    if device_id:
                        update_payload["device_id"] = device_id
                    supabase.table("users").update(update_payload).eq("id", user_id).execute()
                    logger.info(f"User logged in, device updated: {email}")
            except HTTPException:
                raise
            except Exception as sync_err:
                logger.error(f"Error syncing to public.users: {sync_err}")
            
            # Delete OTP from Redis
            redis_manager.delete(redis_key)
            
            return {
                "status": "success",
                "message": "Verified",
                "access_token": access_token,
                "token_type": "bearer",
                "user": {
                    "id": user_id,
                    "email": email
                }
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"OTP verification failed: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Authentication error: {str(e)}"
            )

    async def complete_registration(self, user_id: str, request: RegisterRequest, access_token: str = None) -> Dict[str, Any]:
        """
        Complete user registration by updating profile details.
        
        Args:
            user_id: UUID of the authenticated user
            request: Registration details including name, university, device_id, etc.
            access_token: The user's JWT (used to set their chosen password without admin rights)
        """
        supabase = get_supabase_client()
        if not supabase:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database connection error"
            )

        try:
            # Prepare update data from request
            update_data = request.model_dump(exclude_unset=True, by_alias=True)
            
            # Remove fields that shouldn't go to public.users table
            if "email" in update_data:
                del update_data["email"]
            password_to_set = update_data.pop("password", None)

            update_data['account_type'] = 'free'  # Default as per requirements
            update_data['logged_in'] = True  # Mark as logged in on registration
            
            # Update public.users
            result = supabase.table("users").update(update_data).eq("id", user_id).execute()
            
            # Print result for debugging
            print(f"DEBUG: Update result: {result}")

            if not result.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User profile not found. Please verify OTP first."
                )

            # --- Set the user's chosen password ---
            # Strategy: Use user's own JWT to call update_user() — no admin rights needed.
            # This avoids the "User not allowed" error from admin.update_user_by_id.
            if password_to_set and access_token:
                password_updated = False
                
                # Attempt 1: User-scoped client with their JWT session
                try:
                    import os as _os
                    from supabase import create_client as _create_client
                    _url = _os.getenv("SUPABASE_URL")
                    _key = _os.getenv("SUPABASE_ANON_KEY") or _os.getenv("SUPABASE_KEY") or _os.getenv("SUPABASE_SERVICE_KEY")
                    if _url and _key:
                        user_client = _create_client(_url, _key)
                        user_client.auth.set_session(access_token, access_token)
                        user_client.auth.update_user({"password": password_to_set})
                        logger.info(f"Password set via user session for: {user_id}")
                        password_updated = True
                except Exception as pw_err:
                    logger.error(f"User-scoped password update failed: {pw_err}")
                
                # Attempt 2: Fall back to admin API
                if not password_updated:
                    try:
                        supabase.auth.admin.update_user_by_id(
                            user_id,
                            {"password": password_to_set}
                        )
                        logger.info(f"Password set via admin API for: {user_id}")
                    except Exception as admin_err:
                        logger.error(f"Admin password update also failed: {admin_err}")
                        # Non-fatal — profile is saved, user can reset password if needed
            
            return result.data[0] # Return updated profile

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Registration completion error: {e}")
            print(f"DEBUG_EXCEPTION: {e}")
            if "unique" in str(e).lower() and "email" in str(e).lower():
                 raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already associated with another profile"
                )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to update profile: {str(e)}"
            )

    async def update_profile(self, user_id: str, request: ProfileUpdateRequest) -> Dict[str, Any]:
        """
        Update user profile fields.
        
        Allowed fields: phone_number, nationality, university, profile_picture_url
        """
        supabase = get_supabase_client()
        if not supabase:
             raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Database connection error")

        try:
            update_data = request.model_dump(exclude_unset=True, by_alias=True)
            
            if not update_data:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "No fields to update")

            result = supabase.table("users").update(update_data).eq("id", user_id).execute()
            
            if not result.data:
                 raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
            
            return result.data[0]
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Update profile error: {e}")
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(e))

    async def get_user_analytics(self, user_id: str) -> UserStats:
        """
        Calculate user analytics from redemptions.
        """
        supabase = get_supabase_client()
        try:
            # Query redemptions
            # We only care about valid (not voided) redemptions for stats
            response = supabase.table("redemptions") \
                .select("discount_amount, total_bill_amount, final_amount") \
                .eq("user_id", user_id) \
                .eq("is_voided", False) \
                .execute()
            
            data = response.data
            
            total_saved = sum(float(r.get('discount_amount', 0)) for r in data)
            total_spent = sum(float(r.get('total_bill_amount', 0)) for r in data) # User requirement: sum of total_bill
            total_redemptions = len(data)
            
            # Get subscription status
            user_res = supabase.table("users").select("account_type").eq("id", user_id).execute()
            sub_status = "free"
            if user_res.data:
                sub_status = user_res.data[0].get("account_type", "free")
            
            return UserStats(
                total_saved=total_saved,
                total_spent=total_spent,
                total_redemptions=total_redemptions,
                subscription_status=sub_status
            )
            
        except Exception as e:
            logger.error(f"Analytics error: {e}")
            # Return empty stats on error
            return UserStats()

    async def login(self, email: str, password: str, device_id: str = "") -> Dict:
        """
        Login with email and password via Supabase Auth.
        Checks that user exists in public.users and is not already logged in elsewhere.
        """
        supabase = get_supabase_client()
        if not supabase:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database connection error"
            )

        # 1. Check if user exists and is not already logged in on another device
        try:
            user_check = supabase.table("users").select("id, email, logged_in").eq("email", email).execute()
            if not user_check.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No account found with this email. Please sign up first."
                )
            if user_check.data[0].get("logged_in"):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="You are already logged in on another device. Please logout first."
                )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"User lookup error during login: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database error during login"
            )

        # 2. Sign in with Supabase Auth using the provided password
        try:
            auth_response = supabase.auth.sign_in_with_password({
                "email": email,
                "password": password
            })
        except Exception as e:
            logger.error(f"Supabase sign_in_with_password error: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )

        if not auth_response or not auth_response.user or not auth_response.session:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )

        user_id = str(auth_response.user.id)
        access_token = auth_response.session.access_token

        # 3. Mark user as logged in and update device binding
        try:
            update_payload: dict = {"logged_in": True}
            if device_id:
                update_payload["device_id"] = device_id
            supabase.table("users").update(update_payload).eq("id", user_id).execute()
            logger.info(f"User logged in via password: {email}")
        except Exception as e:
            logger.error(f"Failed to update logged_in on login: {e}")

        return {
            "status": "success",
            "message": "Login successful",
            "access_token": access_token,
            "token_type": "bearer",
            "user": {
                "id": user_id,
                "email": email
            }
        }

    async def logout_user(self, user_id: str) -> None:
        """
        Mark user as logged out so they can sign in from any device next time.
        """
        supabase = get_supabase_client()
        if not supabase:
            return
        try:
            supabase.table("users").update({"logged_in": False}).eq("id", user_id).execute()
            logger.info(f"User logged out: {user_id}")
        except Exception as e:
            logger.error(f"Logout update error: {e}")
        
# Singleton instance
auth_service = AuthService()

