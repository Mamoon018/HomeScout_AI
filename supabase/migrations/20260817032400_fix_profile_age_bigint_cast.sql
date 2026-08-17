-- Fix: profiles.age is bigint, but jsonb ->> returns text.
-- Cast auth metadata age to bigint when creating a profile from a new user.

CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  INSERT INTO public.profiles (id, full_name, age, country, city, zip_code)
  VALUES (
    NEW.id,
    NEW.raw_user_meta_data->>'full_name',
    NULLIF(NEW.raw_user_meta_data->>'age', '')::bigint,
    NEW.raw_user_meta_data->>'country',
    NEW.raw_user_meta_data->>'city',
    NEW.raw_user_meta_data->>'zip_code'
  );

  RETURN NEW;
END;
$$;
