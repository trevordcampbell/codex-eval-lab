mod aggregate;
mod reference;
use std::{hint::black_box, io::{self, Read}, time::Instant};
fn candidate_ns(input:&str,n:usize)->f64 {let t=Instant::now(); for _ in 0..n {black_box(aggregate::aggregate(black_box(input)));} t.elapsed().as_nanos() as f64/n as f64}
fn reference_ns(input:&str,n:usize)->f64 {let t=Instant::now(); for _ in 0..n {black_box(reference::aggregate(black_box(input)));} t.elapsed().as_nanos() as f64/n as f64}
fn main() {
 let mut input=String::new(); io::stdin().read_to_string(&mut input).unwrap();
 let args:Vec<String>=std::env::args().collect();
 let iterations:usize=args[1].parse().unwrap(); let seed:u64=args[2].parse().unwrap();
 for _ in 0..2 {black_box(aggregate::aggregate(black_box(&input))); black_box(reference::aggregate(black_box(&input)));}
 let mut a=Vec::new();let mut b=Vec::new();let mut orders=String::new();
 for block in 0..4 {
   let order=if (seed+block)%2==0 {"ABBA"} else {"BAAB"}; orders.push_str(order);
   for run in order.chars(){if run=='A'{a.push(candidate_ns(&input,iterations));}else{b.push(reference_ns(&input,iterations));}}
 }
 let out=aggregate::aggregate(black_box(&input)); let reference=reference::aggregate(black_box(&input));
 println!("TIMES\t{}",a.iter().map(|x|x.to_string()).collect::<Vec<_>>().join(","));
 println!("REFERENCE_TIMES\t{}",b.iter().map(|x|x.to_string()).collect::<Vec<_>>().join(","));
 println!("ORDER\t{}",orders);
 println!("INVALID\t{}",out.invalid);
 for row in out.rows{println!("{}\t{}\t{}\t{}",row.endpoint,row.count,row.errors,row.bytes);}
 println!("REFERENCE_INVALID\t{}",reference.invalid);
 for row in reference.rows{println!("{}\t{}\t{}\t{}",row.endpoint,row.count,row.errors,row.bytes);}
}
