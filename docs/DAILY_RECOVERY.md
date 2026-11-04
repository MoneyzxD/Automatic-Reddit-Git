# Recuperação da meta diária

Aprovada pelo operador em 04/11/2026: perseguir a meta por canal com novas
execuções durante o dia, preservando qualidade, estado e stack gratuita.

## Comportamento

- Seis oportunidades cron: 01:17, 05:17, 09:17, 13:17, 17:17 e 21:17 UTC.
  Em São Paulo: 22:17 do dia anterior, 02:17, 06:17, 10:17, 14:17 e 18:17.
  GitHub pode atrasar e mantém apenas uma execução pendente por grupo; cron
  é oportunidade de recuperação, não garantia de início nesses horários.
- O grupo de concorrência continua serial, sem cancelar um runner ativo.
- Meta pública continua 3 por data local de cada canal. reserve_days=1 permite
  preencher também amanhã, inclusive quando hoje já está completo.
- Gerador conta os agendados confirmados de hoje e amanhã (limitados à meta
  por data) mais a fila pronta. Dias anteriores e posteriores não preenchem
  o objetivo. Idiomas já cobertos são pulados; tentativas por idioma seguem
  limitadas e indisponibilidade de IA permite prosseguir nos outros idiomas.
- --target explícito continua validação do dia, sem incluir reserva.
- Publicador conserva ID confirmado, bloqueio de upload incerto, intervalos,
  janelas e limite diário. Reserva usa o mesmo publishAt já existente.
- Um excedente indivisível de história pode permanecer na fila privada; não
  se publica acima do limite por data para esvaziá-la.

## Estado e diagnóstico

GETs privados HTTP500/502/503/504 admitem até três tentativas com espera2s/4s.
POSTs não ganham repetição genérica: continuam sob confirmação de assets/markers.
Falhas de autorização/integridade não são convertidas em estado vazio.
Erros agora registram etapa de persistência, método e status HTTP, sem resposta
bruta, URLs assinadas ou valores de credenciais.

Em 03/11, o log antigo preservou somente StateError. A release privada contém
complete-712, complete-713 e complete-715, sem payload714. O checkpoint final
funcionou; a causa exata da falha intermediária não ficou registrada. A proteção
contra 5xx é comprovada em regressão, não prova retroativa da causa do incidente.

## Validação

Baseline com ajuste:1579 testes passaram,14 ignorados. Revisão independente
identificou contagem indevida da reserva com --target explícito; reproduzida e
corrigida, seguida por91 testes focados passando. Testes cobrem reserva quando
hoje já está completo, não reenvio com dois dias completos e exclusão de datas
fora do horizonte. Não houve relaxamento do ScriptGuardian/LanguageTool.

Produção usa o snapshot privado existente; sem bootstrap/reset/limpeza de estado.
A reserva só passa a proteger o dia seguinte depois de gerar, aprovar e enviar
os vídeos. OAuth, cota, indisponibilidade e janelas vencidas continuam limites
reais: configurar recuperação não comprova que a meta pública já foi atingida.
