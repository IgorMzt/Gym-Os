# Limpeza do repositório para a tag v6.0.0

O artefato de distribuição já vem limpo. No repositório Git de desenvolvimento, remova os arquivos históricos/duplicados abaixo antes da tag:

```powershell
git rm V6.13-ARQUIVOS.txt V6.14-ARQUIVOS.txt V6.15-ARQUIVOS.txt V6.16-V6.17-ARQUIVOS.txt
git rm mobile/src/app.json mobile/src/eas.json mobile/src/package.json
git rm mobile/LICENSE
```

Não execute `git rm` em `.env`, `.venv`, caches ou dados locais: eles já são ignorados e podem continuar existindo na sua máquina. Confirme apenas que não estão rastreados:

```powershell
git ls-files .env .venv .pytest_cache
```

O comando não deve retornar arquivos.
