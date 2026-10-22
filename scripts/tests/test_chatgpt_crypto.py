"""OIDC checks against actual maintained JWT/crypto implementations when installed."""
from pathlib import Path
import json
import sys
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
explicit_dependencies = __name__=='__main__' and '--deps' in sys.argv
if explicit_dependencies:
    index=sys.argv.index('--deps')
    sys.path.insert(0,str(Path(sys.argv[index+1]).resolve()))
    del sys.argv[index:index+2]
    import jwt  # Explicit dependency smoke must fail if unavailable.
try:
    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa, ec
except ImportError:
    if explicit_dependencies:
        raise  # An explicit runtime check must exercise crypto, never skip it.
    jwt=None

from chatgpt_auth import ISSUER, verify_id_token, AuthError


@unittest.skipIf(jwt is None,'JWT wheels checked separately in the prepared source runtime')
class IdentityTests(unittest.TestCase):
    def test_missing_crypto_is_a_runtime_fault_instead_of_invalid_identity(self):
        with patch.object(jwt.algorithms,'has_crypto',False):
            with self.assertRaises(AuthError) as failure:
                verify_id_token('unused-token','unused-client',None,{})
        self.assertEqual(failure.exception.status,503)
        self.assertEqual(failure.exception.body['error'],'chatgpt_crypto_unavailable')
        self.assertEqual(failure.exception.diagnostic['identityReason'],'crypto_unavailable')

    def test_signature_algorithm_nonce_audience_issuer_expiry_and_subject(self):
        for algorithm in ('RS256','ES256'):
            with self.subTest(algorithm=algorithm):
                key=rsa.generate_private_key(public_exponent=65537,key_size=2048) if algorithm=='RS256' else ec.generate_private_key(ec.SECP256R1())
                adapter=jwt.algorithms.RSAAlgorithm if algorithm=='RS256' else jwt.algorithms.ECAlgorithm
                jwk=json.loads(adapter.to_jwk(key.public_key()));jwk.update(kid='example-key',alg=algorithm,use='sig')
                claims=dict(iss=ISSUER,aud='issued-client',sub='verified-subject',iat=int(time.time()),exp=int(time.time())+600,nonce='fresh-nonce')
                def encoded(value):return jwt.encode(value,key,algorithm=algorithm,headers=dict(kid='example-key'))
                def verify(token,**kw):return verify_id_token(token,'issued-client',kw.get('nonce','fresh-nonce'),dict(keys=[jwk]),subject=kw.get('subject'))
                self.assertEqual(verify(encoded(claims))['sub'],'verified-subject')
                for change,reason in ((dict(iss='https://example.invalid'),'issuer'),(dict(aud='another-client'),'audience'),
                        (dict(exp=int(time.time())-120),'expired'),(dict(nonce='other'),'nonce'),(dict(azp='other'),'authorized_party')):
                    with self.assertRaises(AuthError) as failure:verify(encoded(claims|change))
                    self.assertEqual(failure.exception.diagnostic['identityReason'],reason)
                    self.assertNotIn('another-client',json.dumps(failure.exception.diagnostic))
                    self.assertNotIn('verified-subject',json.dumps(failure.exception.diagnostic))
                with self.assertRaises(AuthError) as failure:verify(encoded(claims),subject='different-account')
                self.assertEqual(failure.exception.diagnostic['identityReason'],'subject')
                with self.assertRaises(AuthError):verify(jwt.encode(claims,'shared-secret',algorithm='HS256',headers=dict(kid='example-key')))
                other=rsa.generate_private_key(public_exponent=65537,key_size=2048) if algorithm=='RS256' else ec.generate_private_key(ec.SECP256R1())
                with self.assertRaises(AuthError):verify(jwt.encode(claims,other,algorithm=algorithm,headers=dict(kid='example-key')))


if __name__=='__main__':unittest.main()
