-- Create public Supabase Storage bucket for user profile pictures.
-- Bucket is public so <Image source={{uri}}> renders without auth headers.
-- Mirrors user-verification-documents bucket creation in add_manual_review_signup.sql.

INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
  'user-profile-images',
  'user-profile-images',
  true,
  5242880,
  ARRAY['image/jpeg', 'image/png', 'image/webp']
)
ON CONFLICT (id) DO UPDATE
SET
  public = EXCLUDED.public,
  file_size_limit = EXCLUDED.file_size_limit,
  allowed_mime_types = EXCLUDED.allowed_mime_types;

-- Allow anyone to read from the bucket (public read) and authenticated users to upload
-- their own files under a path that matches their user id.

DROP POLICY IF EXISTS "Public read access to profile images" ON storage.objects;
CREATE POLICY "Public read access to profile images"
  ON storage.objects FOR SELECT
  USING (bucket_id = 'user-profile-images');

DROP POLICY IF EXISTS "Users can upload their own profile images" ON storage.objects;
CREATE POLICY "Users can upload their own profile images"
  ON storage.objects FOR INSERT
  WITH CHECK (
    bucket_id = 'user-profile-images'
    AND (auth.uid()::text = (storage.foldername(name))[1])
  );

DROP POLICY IF EXISTS "Users can update their own profile images" ON storage.objects;
CREATE POLICY "Users can update their own profile images"
  ON storage.objects FOR UPDATE
  USING (
    bucket_id = 'user-profile-images'
    AND (auth.uid()::text = (storage.foldername(name))[1])
  );

DROP POLICY IF EXISTS "Users can delete their own profile images" ON storage.objects;
CREATE POLICY "Users can delete their own profile images"
  ON storage.objects FOR DELETE
  USING (
    bucket_id = 'user-profile-images'
    AND (auth.uid()::text = (storage.foldername(name))[1])
  );

NOTIFY pgrst, 'reload schema';
