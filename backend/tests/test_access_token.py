import pytest

from src.services.auth.access_token import TokenVerificationError
from tests.conftest import mint_access_token, make_access_token_verifier


def test_verify_accepts_es256_token_with_matching_audience():
    verifier = make_access_token_verifier()
    token = mint_access_token()
    verified = verifier.verify(token)
    assert verified.algorithm == "ES256"
    assert verified.audience_matched is True
    assert verified.subject == "user-1"


def test_verify_rejects_wrong_audience():
    verifier = make_access_token_verifier()
    token = mint_access_token(audience="someone-else")
    with pytest.raises(TokenVerificationError):
        verifier.verify(token)


def test_verify_rejects_missing_audience():
    verifier = make_access_token_verifier()
    token = mint_access_token(include_audience=False)
    with pytest.raises(TokenVerificationError):
        verifier.verify(token)


def test_verify_rejects_hs256_even_if_decodeable():
    verifier = make_access_token_verifier()
    token = mint_access_token(
        algorithm="HS256",
        key="0123456789abcdef0123456789abcdef",
    )
    with pytest.raises(TokenVerificationError, match="allowed algorithm"):
        verifier.verify(token)
