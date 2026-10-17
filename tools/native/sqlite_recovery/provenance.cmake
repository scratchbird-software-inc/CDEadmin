file(READ "${TEMPLATE}" provenance)
file(SHA256 "${LIBRARY}" library_sha256)
string(JSON provenance SET "${provenance}" library_sha256 "\"${library_sha256}\"")
file(WRITE "${LIBRARY}.json" "${provenance}\n")
