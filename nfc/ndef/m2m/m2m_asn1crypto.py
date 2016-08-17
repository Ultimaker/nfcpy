#! /usr/bin/python3

"""Format for M2M certificates as defined in
Signature Record Type Definition
Technical Specification
Version 2.0
2014-11-26
[SIGNATURE]
NFC Forum (tm)

[SEC1]:
STANDARDS FOR EFFICIENT CRYPTOGRAPHY
SEC 1: Elliptic Curve Cryptography
September 20, 2000
Version 1.0
http://www.secg.org/SEC1-Ver-1.0.pdf"""


# coding: utf-8
from __future__ import unicode_literals, division, absolute_import, print_function

import base64
import enum
import subprocess
from datetime import datetime, timedelta
import inspect
import re
import sys
import textwrap
import time

from asn1crypto import x509, keys, core
from asn1crypto.util import int_to_bytes, int_from_bytes, timezone
from oscrypto import asymmetric, util

from asn1crypto.core import Sequence, SequenceOf, ObjectIdentifier, Boolean, OctetString, Choice, \
    PrintableString, UTF8String, IA5String, Integer
from asn1crypto.x509 import ExtensionId

from binascii import hexlify

# TODO: SIZEs are not encoded yet.

class Extension(Sequence):
    _fields = [
        ('extnID', ExtensionId),
        ('criticality', Boolean, {'default': False}),
        ('extnValue', OctetString),
    ]


class X509Extensions(SequenceOf):
    _child_spec = Extension


class AttributeValue(Choice):
    _alternatives = [
        ('country', PrintableString),
        ('organization', UTF8String),
        ('organizationalUnit', UTF8String),
        ('distinguishedNameQualifier', PrintableString),
        ('stateOrProvince', UTF8String),
        ('locality', UTF8String),
        ('commonName', UTF8String),
        ('serialNumber', PrintableString),
        ('domainComponent', IA5String),
        ('registeredId', ObjectIdentifier),
        ('octetsName', OctetString),
    ]


class Name(SequenceOf):
    _child_spec = AttributeValue


class GeneralName(Choice):
    _alternatives = [
        ('rfc822Name', IA5String),
        ('dNSName',    IA5String),
        ('directoryName', Name),
        ('uniformResourceIdentifier', IA5String),
        ('iPAddress', OctetString),
        ('registeredID', ObjectIdentifier),
    ]


class AuthkeyID(Sequence):
    _fields = [
        ('keyIdentified', OctetString, {'optional':True}),
        ('authCertIssuer', GeneralName, {'optional':True}),
        ('authCertSerialNum', OctetString, {'optional':True}),
    ]


class Version(Integer):
    # _map = {
    #     0: 'v1',
    # }
    pass

class CaPkAlgorithm(ObjectIdentifier):
    _map = {'2.16.840.1.114513.1.0': 'ecdsa-with-sha256-secp192r1',
            '2.16.840.1.114513.1.1': 'ecdsa-with-sha256-secp224r1',
            '2.16.840.1.114513.1.2': 'ecdsa-with-sha256-sect233k1',
            '2.16.840.1.114513.1.3': 'ecdsa-with-sha256-sect233r1',
            '2.16.840.1.114513.1.4': 'ecqv-with-sha256-secp192r1',
            '2.16.840.1.114513.1.5': 'ecqv-with-sha256-secp224r1',
            '2.16.840.1.114513.1.6': 'ecqv-with-sha256-sect233k1',
            '2.16.840.1.114513.1.7': 'ecqv-with-sha256-sect233r1',
            '2.16.840.1.114513.1.8': 'rsa-with-sha256',
            '2.16.840.1.114513.1.9': 'ecdsa-with-sha256-secp256r1',
            '2.16.840.1.114513.1.10': 'ecqv-with-sha256-secp256r1',}

class TBSCertificate(Sequence):
    _fields = [
        ('version', Integer), #Version, {'default':Version('v1')}),
        ('serialNumber', OctetString),
        ('cAAlgorithm', CaPkAlgorithm, {'optional':True}),
        ('cAAlgParams', OctetString, {'optional':True}),
        ('issuer', Name, {'optional':True}),
        ('validFrom', OctetString, {'optional':True}),
        ('validDuration', OctetString, {'optional':True}),
        ('subject', Name),
        ('pKAlgorithm', CaPkAlgorithm, {'optional':True}),
        ('pKAlgParams', OctetString, {'optional':True}),
        ('pubKey', OctetString, {'optional':True}),
        ('authKeyId', AuthkeyID, {'optional':True}),
        ('subjKeyId', OctetString, {'optional':True}),
        ('keyUsage', OctetString, {'optional':True}),
        ('basicConstraints', Integer, {'optional':True}),
        ('certificatePolicy', ObjectIdentifier, {'optional':True}),
        ('subjectAltName', GeneralName, {'optional':True}),
        ('issuerAltName', GeneralName, {'optional':True}),
        ('extendedKeyUsage', ObjectIdentifier, {'optional':True}),
        ('authInfoAccessOCSP', IA5String, {'optional':True}),
        ('cRLDistribPointURI', IA5String, {'optional':True}),
        ('x509extensions', X509Extensions, {'optional':True}),
    ]


class Certificate(Sequence):
    _fields = [
        ('tbsCertificate', TBSCertificate),
        ('cACalcValue', OctetString)
    ]


class AlgorithmObjectIdentifiers(enum.Enum):
    ecdsa_with_sha256_secp192r1     = ObjectIdentifier("2.16.840.1.114513.1.0")
    ecdsa_with_sha256_secp224r1     = ObjectIdentifier("2.16.840.1.114513.1.1")
    ecdsa_with_sha256_sect233k1     = ObjectIdentifier("2.16.840.1.114513.1.2")
    ecdsa_with_sha256_sect233r1     = ObjectIdentifier("2.16.840.1.114513.1.3")
    ecqv_with_sha256_secp192r1      = ObjectIdentifier("2.16.840.1.114513.1.4")
    ecqv_with_sha256_secp224r1      = ObjectIdentifier("2.16.840.1.114513.1.5")
    ecqv_with_sha256_sect233k1      = ObjectIdentifier("2.16.840.1.114513.1.6")
    ecqv_with_sha256_sect233r1      = ObjectIdentifier("2.16.840.1.114513.1.7")
    rsa_with_sha256                 = ObjectIdentifier("2.16.840.1.114513.1.8")
    ecdsa_with_sha256_secp256r1     = ObjectIdentifier("2.16.840.1.114513.1.9")
    ecqv_with_sha256_secp256r1      = ObjectIdentifier("2.16.840.1.114513.1.10")


class FieldElement(OctetString): pass # See [SEC1], Clause 2.3.5
class ECPoint(OctetString): pass # See [SEC1], Clause 2.3.3

class Y_Choice(Choice):
    _alternatives = [
        ('b', Boolean,
         'f', FieldElement) # See [SEC1]
    ]


class ECDSA_Sig_Value(Sequence):
    _fields = [
        ('r', Integer),
        ('s', Integer),
        ('a', Integer, {'optional':True}),
        ('y', Y_Choice, {'optional':True}),
    ]


class ECDSA_Full_R(Sequence):
    _fields = [
        ('r', ECPoint), # See [SEC1], Clause 2.3.3
        ('s', Integer),
    ]

class RSA_Signature(OctetString): pass

class RSAPublicKey(Sequence):
    _fields = [
        ('modulus', Integer), # n
        ('publicExponent', Integer) # e
    ]


class ECDSA_Signature(Choice):
    _alternatives = [
        ('two-ints-plus', ECDSA_Sig_Value),
        ('point-int', ECDSA_Full_R),
    ]

if sys.version_info < (3,):
    int_types = (int, long)  # noqa
    str_cls = unicode  # noqa
    byte_cls = str
else:
    int_types = (int,)
    str_cls = str
    byte_cls = bytes


__version__ = '0.14.2'
__version_info__ = (0, 14, 2)


def _writer(func):
    """
    Decorator for a custom writer, but a default reader
    """

    name = func.__name__
    return property(fget=lambda self: getattr(self, '_%s' % name), fset=func)

class CertificateBuilder(object):
    _version = 0
    _serial_number = None
    _ca_algorithm = None
    _ca_algorithm_parameters = None
    _issuer = None
    _valid_from = None
    _valid_duration = None
    _subject = None
    _pk_algorithm = None
    _pk_algorithm_parameters = None
    _public_key = None
    _authkey_id = None
    _subject_key_id = None
    _key_usage = None
    _basic_constraints = None
    _certificate_policy = None
    _subject_alternative_name = None
    _issuer_alternative_name = None
    _extended_key_usage = None
    _auth_info_access_ocsp = None
    _crl_distribution_point_uri = None
    _x509_extensions = None

    _self_signed = False


    def __init__(self, subject, subject_public_key):
        """
        Unless changed, certificates will use SHA-256 for the signature,
        and will be valid from the moment created for one year. The serial
        number will be generated from the current time and a random number.
        :param subject:
            An asn1crypto.x509.Name object, or a dict - see the docstring
            for .subject for a list of valid options
        :param subject_public_key:
            An asn1crypto.keys.PublicKeyInfo object containing the public key
            the certificate is being issued for
        """

        self.subject = subject
        self.public_key = subject_public_key
        self.ca = False

        self._hash_algo = 'sha256'
        self._other_extensions = {}

    @_writer
    def self_signed(self, value):
        """
        A bool - if the certificate should be self-signed.
        """

        self._self_signed = bool(value)

        if self._self_signed:
            self._issuer = None

    @_writer
    def serial_number(self, value):
        """
        An int representable in 160 bits or less - must uniquely identify
        this certificate when combined with the issuer name.
        """

        if not isinstance(value, int_types):
            raise TypeError(_pretty_message(
                '''
                serial_number must be an integer, not %s
                ''',
                _type_name(value)
            ))

        if value < 0:
            raise ValueError(_pretty_message(
                '''
                serial_number must be a non-negative integer, not %s
                ''',
                repr(value)
            ))

        if len(int_to_bytes(value)) > 20:
            required_bits = len(int_to_bytes(value)) * 8
            raise ValueError(_pretty_message(
                '''
                serial_number must be an integer that can be represented by a
                160-bit number, specified requires %s
                ''',
                required_bits
            ))

        self._serial_number = value

    @_writer
    def ca_algorithm(self, value):
        self._ca_algorithm = value

    @_writer
    def ca_algorithm_parameters(self, value):
        self._ca_algorithm_parameters = value

    @_writer
    def issuer(self, value):
        """
        m2m.Name
        """

        self._issuer = value

    @_writer
    def valid_from(self, value):
        """
        A datetime.datetime object of when the certificate becomes valid.
        """

        if not isinstance(value, datetime):
            raise TypeError(_pretty_message(
                '''
                valid_from must be an instance of datetime.datetime, not %s
                ''',
                _type_name(value)
            ))

        self._valid_from = (value - datetime.utcfromtimestamp(0)).total_seconds().to_bytes(5, byteorder='big')

    @_writer
    def valid_duration(self, value):
        """
        A datetime.datetime object of when the certificate is last to be
        considered valid.
        """

        if not isinstance(value, timedelta):
            raise TypeError(_pretty_message(
                '''
                valid_duration must be an instance of datetime.timedelta, not %s
                ''',
                _type_name(value)
            ))

        self._valid_duration = value.total_seconds().to_bytes(5, byteorder='big')

    @_writer
    def subject(self, value):
        """
        A Name object
        """

        is_dict = isinstance(value, dict)
        if not isinstance(value, Name):
            raise TypeError(_pretty_message(
                '''
                subject must be an instance of m2m.Name,
                not %s
                ''',
                _type_name(value)
            ))

        self._subject = value

    @_writer
    def pk_algorithm(self, value):
        self._pk_algorithm = value

    @_writer
    def pk_algorithm_parameters(self, value):
        self._pk_algorithm_parameters = value

    @_writer
    def public_key(self, value):
        """
        A byte sequence containing the public key
        """
        if not isinstance(value, bytearray) and not isinstance(value, bytes):
            raise TypeError(_pretty_message(
                '''
                public_key must be an sequence of bytes,
                not %s
                ''',
                _type_name(value)
            ))

        self._public_key = value

    @_writer
    def authkey_id(self, value):
        self._authkey_id = value

    @_writer
    def subject_key_id(self, value):
        self._subject_key_id = value

    @_writer
    def key_usage(self, value):
        self._key_usage = value

    @_writer
    def basic_constraints(self, value):
        self._basic_constraints = value

    @_writer
    def certificate_policy(self, value):
        self._certificate_policy = value

    @_writer
    def subject_alternative_name(self, value):
        self._subject_alternative_name = value

    @_writer
    def issuer_alternative_name(self, value):
        self._issuer_alternative_name = value

    @_writer
    def extended_key_usage(self, value):
        self._extended_key_usage = value

    @_writer
    def auth_info_access_ocsp(self, value):
        self._auth_info_access_ocsp = value

    @_writer
    def crl_distribution_point_uri(self, value):
        self._crl_distribution_point_uri = value

    @_writer
    def x509_extensions(self, value):
        self._x509_extensions = value

    def build(self, signing_private_key_path):
        """
        Validates the certificate information, constructs the ASN.1 structure
        and then signs it
        :param signing_private_key:
            path to a .pem file with a private key
        :return:
            An m2m.Certificate object of the newly signed
            certificate
        """
        if self._self_signed is not True and self._issuer is None:
            raise ValueError(_pretty_message(
                '''
                Certificate must be self-signed, or an issuer must be specified
                '''
            ))

        if self._self_signed:
            self._issuer = self._subject

        if self.serial_number is None:
            time_part = int_to_bytes(int(time.time()))
            random_part = util.rand_bytes(4)
            self.serial_number = int_from_bytes(time_part + random_part)

        # Only re non-optionals are always in this dict
        properties = {
            'version':Integer(value=self._version),
            'serialNumber':OctetString(value=self.serial_number.to_bytes(20, byteorder='big')),
            'subject':self.subject,
        }

        # Optional fields are only added if they're not None
        if self.ca_algorithm is not None:
            properties['cAAlgorithm'] = self.ca_algorithm
        if self.ca_algorithm_parameters is not None:
            properties['cAAlgParams'] = OctetString(value=self.ca_algorithm_parameters)
        if self.issuer is not None:
            properties['issuer'] = self.issuer
        if self.valid_from is not None:
            properties['validFrom'] = self.valid_from
        if self.valid_duration is not None:
            properties['validDuration'] =  self.valid_duration
        if self.pk_algorithm is not None:
            properties['pKAlgorithm'] = self.pk_algorithm
        if self.pk_algorithm_parameters is not None:
            properties['pKAlgParams'] = OctetString(value=self.pk_algorithm_parameters)
        if self.public_key is not None:
            properties['pubKey'] = OctetString(value=self.public_key)
        if self.authkey_id is not None:
            properties['authKeyId'] = self.authkey_id
        if self.subject_key_id is not None:
            properties['subjKeyId'] = OctetString(value=self.subject_key_id)
        if self.key_usage is not None:
            properties['keyUsage'] = OctetString(value=self.key_usage)
        if self.basic_constraints is not None:
            properties['basicConstraints'] =  Integer(value=self.basic_constraints)
        if self.certificate_policy is not None:
            properties['certificatePolicy'] = self.certificate_policy
        if self.subject_alternative_name is not None:
            properties['subjectAltName'] = self.subject_alternative_name
        if self.issuer_alternative_name is not None:
            properties['issuerAltName'] = self.issuer_alternative_name
        if self.extended_key_usage is not None:
            properties['extendedKeyUsage'] = self.extended_key_usage
        if self.auth_info_access_ocsp is not None:
            properties['authInfoAccessOCSP'] = self.auth_info_access_ocsp
        if self.crl_distribution_point_uri is not None:
            properties['cRLDistribPointURI'] = self.crl_distribution_point_uri
        if self.x509_extensions is not None:
            properties['x509extensions'] = self.x509_extensions

        # import ipdb; ipdb.set_trace()
        # break /usr/local/lib/python3.5/dist-packages/asn1crypto/core.py:2786
        tbs_cert = TBSCertificate(properties)

        bytes_to_sign = tbs_cert.dump()
        signature = generate_signature(bytes_to_sign, signing_private_key_path)

        return Certificate({
            'tbsCertificate': tbs_cert,
            'cACalcValue': signature
        })

def _pretty_message(string, *params):
    """
    Takes a multi-line string and does the following:
     - dedents
     - converts newlines with text before and after into a single line
     - strips leading and trailing whitespace
    :param string:
        The string to format
    :param *params:
        Params to interpolate into the string
    :return:
        The formatted string
    """

    output = textwrap.dedent(string)

    # Unwrap lines, taking into account bulleted lists, ordered lists and
    # underlines consisting of = signs
    if output.find('\n') != -1:
        output = re.sub('(?<=\\S)\n(?=[^ \n\t\\d\\*\\-=])', ' ', output)

    if params:
        output = output % params

    output = output.strip()

    return output


def _type_name(value):
    """
    :param value:
        A value to get the object name of
    :return:
        A unicode string of the object name
    """

    if inspect.isclass(value):
        cls = value
    else:
        cls = value.__class__
    if cls.__module__ in set(['builtins', '__builtin__']):
        return cls.__name__
    return '%s.%s' % (cls.__module__, cls.__name__)


def generate_signature(to_be_signed_bytes, private_key_path='private.pem'):
    """openssl dgst -sha256 -sign private.pem -out signature.der message.txt"""
    byte_path = "/tmp/to_be_signed.tmp"
    with open(byte_path, 'wb') as byte_file:
        byte_file.write(to_be_signed_bytes)

    signature_path = "/tmp/signature.der"
    proc = subprocess.Popen(['openssl', 'dgst', '-sha256', '-sign', private_key_path, '-out', signature_path, byte_path],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (out, err) = proc.communicate()

    if not err:
        with open(signature_path, 'rb') as signature_file:
            signature = signature_file.read()
            return signature
    else:
        raise OSError(err)

def verify_signature(signed_bytes, signature, public_key_path='public.pem'):
    """openssl dgst -sha256 -verify public.pem -signature signature.der message.txt"""
    byte_path = "/tmp/signed.tmp"
    with open(byte_path, 'wb') as byte_file:
        byte_file.write(signed_bytes)

    signature_path = "/tmp/signature.der"
    with open(signature_path, 'wb') as signature_file:
        signature_file.write(signature)

    proc = subprocess.Popen(['openssl', 'dgst', '-sha256', '-verify', public_key_path, '-signature', signature_path, byte_path],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (out, err) = proc.communicate()
    if not err:
        return out.strip() == b"Verified OK"
    else:
        raise OSError(err)

if __name__ == "__main__":
    subject = Name()
    subject[0] = AttributeValue(name='country', value=PrintableString(value='US'))
    subject[1] = AttributeValue(name='organization', value=UTF8String(value='ACME corp.'))
    subject[2] = AttributeValue(name='locality', value=UTF8String(value='Fairfield'))

    pubkey = base64.decodebytes(b'MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEyCjVqzDqCn5KS2QYmD6bCajY1L8+\nla/50oJSDw5nKZm9zqeUIxwpl215Gz+aeBJOEHEC06fHjnb3TNdQcu1aKg==')
    builder = CertificateBuilder(subject, pubkey)

    builder.version = 0
    builder.serial_number = 123456789
    builder.ca_algorithm = "1.2.840.10045.4.3.2" # ECDSA with SHA256, see http://oid-info.com/get/1.2.840.10045.4.3.2
    builder.ca_algorithm_parameters = base64.decodebytes(b'BggqhkjOPQMBBw==') # EC PARAMETERS
                             # Parameters for the elliptic curve: http://oid-info.com/get/1.2.840.10045.3.1.7
    builder.self_signed = True #builder.issuer = subject
    builder.pk_algorithm = pKAlgorithm="1.2.840.10045.4.3.2"  # Same as cAAlgorithm
    builder.subject_key_id = int(1).to_bytes(1, byteorder='big')
    builder.key_usage = 0b10100000.to_bytes(1, byteorder='big') # digitalSignature & keyEncipherment bit set
    # builder.basicConstraints =  # Omit if end-entity cert
    builder.certificate_policy = "2.5.29.32.0"  # Anypolicy: http://www.oid-info.com/get/2.5.29.32.0
    builder.extended_key_usage = "2.16.840.1.114513.29.37" # Optional in ASN1 but explanation in spec says it MUST be present. Variant of X509 http://www.oid-info.com/get/2.5.29.37.0
    # builder.crl_distribution_point_uri =  IA5String(u'www.acme.com/')

    orig_cert = builder.build(signing_private_key_path="private.pem")

    orig_dump = orig_cert.dump()
    orig_dump_hex = hexlify(orig_dump)
    print(orig_dump_hex)
    print(len(orig_dump))

    decoded_cert = Certificate.load(orig_dump)
    assert decoded_cert.dump() == orig_dump
    assert len(orig_cert.children) == 2
    assert len(decoded_cert.children) == 2
