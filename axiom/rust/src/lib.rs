use blake2::digest::consts::U32;
use blake2::{Blake2b, Digest};

pub fn compute_cid(data: &[u8]) -> String {
    let mut hasher = Blake2b::<U32>::new();
    hasher.update(data);
    let res = hasher.finalize();
    format!("b2b256:{}", hex::encode(res))
}
