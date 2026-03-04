from rest_framework import serializers


class KakaoLoginSerializer(serializers.Serializer):
    code = serializers.CharField()


class AppleLoginSerializer(serializers.Serializer):
    code = serializers.CharField()


class TokenOutputSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()
