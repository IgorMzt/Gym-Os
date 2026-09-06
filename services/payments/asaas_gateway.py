import json, os
from urllib import request, parse, error

class GatewayError(RuntimeError): pass

class AsaasGateway:
    def __init__(self):
        self.base_url=os.getenv('ASAAS_BASE_URL','https://api-sandbox.asaas.com/v3').rstrip('/')
        self.api_key=os.getenv('ASAAS_API_KEY','').strip()
    @property
    def configurado(self): return bool(self.api_key)
    def _call(self, method, path, payload=None, query=None):
        if not self.api_key: raise GatewayError('ASAAS_API_KEY não configurada.')
        url=self.base_url+path
        if query: url += '?' + parse.urlencode(query)
        body=json.dumps(payload).encode() if payload is not None else None
        req=request.Request(url,data=body,method=method,headers={'access_token':self.api_key,'Content-Type':'application/json','User-Agent':'PanoGym-OS/5.1A'})
        try:
            with request.urlopen(req,timeout=20) as resp: return json.loads(resp.read().decode() or '{}')
        except error.HTTPError as exc:
            raw=exc.read().decode(errors='replace')
            try:
                data=json.loads(raw); msgs=[e.get('description','') for e in data.get('errors',[])]; detail='; '.join(x for x in msgs if x) or raw
            except Exception: detail=raw
            raise GatewayError(f'Asaas HTTP {exc.code}: {detail[:500]}') from exc
        except Exception as exc: raise GatewayError(f'Falha de comunicação com Asaas: {exc}') from exc
    def localizar_cliente(self, pessoa_id):
        d=self._call('GET','/customers',query={'externalReference':str(pessoa_id),'limit':1}); arr=d.get('data') or []; return arr[0] if arr else None
    def criar_cliente(self,pessoa):
        payload={'name':pessoa['nome'],'cpfCnpj':''.join(c for c in (pessoa.get('cpf') or '') if c.isdigit()),'externalReference':str(pessoa['id']),'notificationDisabled':True}
        if pessoa.get('email'): payload['email']=pessoa['email']
        tel=''.join(c for c in (pessoa.get('telefone') or '') if c.isdigit())
        if tel: payload['mobilePhone']=tel
        return self._call('POST','/customers',payload)
    def criar_cobranca_pix(self,customer_id,valor_centavos,vencimento,referencia):
        return self._call('POST','/payments',{'customer':customer_id,'billingType':'PIX','value':round(valor_centavos/100,2),'dueDate':vencimento,'externalReference':referencia,'description':'Mensalidade academia'})
    def obter_pix(self,payment_id): return self._call('GET',f'/payments/{payment_id}/pixQrCode')
