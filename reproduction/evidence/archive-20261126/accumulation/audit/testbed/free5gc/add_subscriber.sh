#!/bin/bash
# Provision free5GC subscribers imsi-20893000000000{1..N} via the webui REST API (admin/free5gc defaults).
N=${1:-2}
export DOCKER_CONTEXT=${DOCKER_CONTEXT:-colima-recover5g}
TOK=$(docker exec f5g-probe curl -s -X POST http://webui:5000/api/login -H 'Content-Type: application/json' -d '{"username":"admin","password":"free5gc"}' | sed -n 's/.*"access_token":"\([^"]*\)".*/\1/p')
for i in $(seq 1 $N); do
IMSI=imsi-20893000000000$i
BODY=$(cat <<JSON
{"userNumber":1,"ueId":"$IMSI","plmnID":"20893",
"AuthenticationSubscription":{"authenticationMethod":"5G_AKA","permanentKey":{"permanentKeyValue":"8baf473f2f8fd09487cccbd7097c6862","encryptionKey":0,"encryptionAlgorithm":0},"sequenceNumber":"000000000023","authenticationManagementField":"8000","milenage":{"op":{"opValue":"","encryptionKey":0,"encryptionAlgorithm":0}},"opc":{"opcValue":"8e27b6af0e692e750f32667a3b14605d","encryptionKey":0,"encryptionAlgorithm":0}},
"AccessAndMobilitySubscriptionData":{"gpsis":["msisdn-"],"subscribedUeAmbr":{"uplink":"1 Gbps","downlink":"2 Gbps"},"nssai":{"defaultSingleNssais":[{"sst":1,"sd":"010203"}],"singleNssais":[{"sst":1,"sd":"112233"}]}},
"SessionManagementSubscriptionData":[{"singleNssai":{"sst":1,"sd":"010203"},"dnnConfigurations":{"internet":{"pduSessionTypes":{"defaultSessionType":"IPV4","allowedSessionTypes":["IPV4"]},"sscModes":{"defaultSscMode":"SSC_MODE_1","allowedSscModes":["SSC_MODE_2","SSC_MODE_3"]},"5gQosProfile":{"5qi":9,"arp":{"priorityLevel":8,"preemptCap":"","preemptVuln":""},"priorityLevel":8},"sessionAmbr":{"uplink":"1000 Mbps","downlink":"1000 Mbps"}}}}],
"SmfSelectionSubscriptionData":{"subscribedSnssaiInfos":{"01010203":{"dnnInfos":[{"dnn":"internet"}]}}},
"AmPolicyData":{"subscCats":["free5gc"]},
"SmPolicyData":{"smPolicySnssaiData":{"01010203":{"snssai":{"sst":1,"sd":"010203"},"smPolicyDnnData":{"internet":{"dnn":"internet"}}}}},
"FlowRules":[],"QosFlows":[],"ChargingDatas":[]}
JSON
)
echo "$IMSI: $(docker exec f5g-probe curl -s -o /dev/null -w '%{http_code}' -X POST http://webui:5000/api/subscriber/$IMSI/20893 -H "Token: $TOK" -H 'Content-Type: application/json' -d "$BODY")"
done
