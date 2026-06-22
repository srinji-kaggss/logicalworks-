// Lean compiler output
// Module: ExcellentCode.Framework
// Imports: public import Init public meta import Init
#include <lean/lean.h>
#if defined(__clang__)
#pragma clang diagnostic ignored "-Wunused-parameter"
#pragma clang diagnostic ignored "-Wunused-label"
#elif defined(__GNUC__) && !defined(__CLANG__)
#pragma GCC diagnostic ignored "-Wunused-parameter"
#pragma GCC diagnostic ignored "-Wunused-label"
#pragma GCC diagnostic ignored "-Wunused-but-set-variable"
#endif
#ifdef __cplusplus
extern "C" {
#endif
uint8_t lean_nat_dec_eq(lean_object*, lean_object*);
uint8_t lean_nat_dec_le(lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_ctorIdx(uint8_t);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_ctorIdx___boxed(lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_toCtorIdx(uint8_t);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_toCtorIdx___boxed(lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_ctorElim___redArg(lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_ctorElim___redArg___boxed(lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_ctorElim(lean_object*, lean_object*, uint8_t, lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_ctorElim___boxed(lean_object*, lean_object*, lean_object*, lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_referential__truth_elim___redArg(lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_referential__truth_elim___redArg___boxed(lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_referential__truth_elim(lean_object*, uint8_t, lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_referential__truth_elim___boxed(lean_object*, lean_object*, lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_specification__fidelity_elim___redArg(lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_specification__fidelity_elim___redArg___boxed(lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_specification__fidelity_elim(lean_object*, uint8_t, lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_specification__fidelity_elim___boxed(lean_object*, lean_object*, lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_type__soundness_elim___redArg(lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_type__soundness_elim___redArg___boxed(lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_type__soundness_elim(lean_object*, uint8_t, lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_type__soundness_elim___boxed(lean_object*, lean_object*, lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_precondition__correctness_elim___redArg(lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_precondition__correctness_elim___redArg___boxed(lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_precondition__correctness_elim(lean_object*, uint8_t, lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_precondition__correctness_elim___boxed(lean_object*, lean_object*, lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_postcondition__correctness_elim___redArg(lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_postcondition__correctness_elim___redArg___boxed(lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_postcondition__correctness_elim(lean_object*, uint8_t, lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_postcondition__correctness_elim___boxed(lean_object*, lean_object*, lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_invariant__preservation_elim___redArg(lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_invariant__preservation_elim___redArg___boxed(lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_invariant__preservation_elim(lean_object*, uint8_t, lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_invariant__preservation_elim___boxed(lean_object*, lean_object*, lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_totality__or__controlled__partiality_elim___redArg(lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_totality__or__controlled__partiality_elim___redArg___boxed(lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_totality__or__controlled__partiality_elim(lean_object*, uint8_t, lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_totality__or__controlled__partiality_elim___boxed(lean_object*, lean_object*, lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_boundary__completeness_elim___redArg(lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_boundary__completeness_elim___redArg___boxed(lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_boundary__completeness_elim(lean_object*, uint8_t, lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_boundary__completeness_elim___boxed(lean_object*, lean_object*, lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_compositionality_elim___redArg(lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_compositionality_elim___redArg___boxed(lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_compositionality_elim(lean_object*, uint8_t, lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_compositionality_elim___boxed(lean_object*, lean_object*, lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_minimal__sufficient__complexity_elim___redArg(lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_minimal__sufficient__complexity_elim___redArg___boxed(lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_minimal__sufficient__complexity_elim(lean_object*, uint8_t, lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_minimal__sufficient__complexity_elim___boxed(lean_object*, lean_object*, lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_algorithmic__efficiency_elim___redArg(lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_algorithmic__efficiency_elim___redArg___boxed(lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_algorithmic__efficiency_elim(lean_object*, uint8_t, lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_algorithmic__efficiency_elim___boxed(lean_object*, lean_object*, lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_state__minimization_elim___redArg(lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_state__minimization_elim___redArg___boxed(lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_state__minimization_elim(lean_object*, uint8_t, lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_state__minimization_elim___boxed(lean_object*, lean_object*, lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_data__model__truth_elim___redArg(lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_data__model__truth_elim___redArg___boxed(lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_data__model__truth_elim(lean_object*, uint8_t, lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_data__model__truth_elim___boxed(lean_object*, lean_object*, lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_error__semantics_elim___redArg(lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_error__semantics_elim___redArg___boxed(lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_error__semantics_elim(lean_object*, uint8_t, lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_error__semantics_elim___boxed(lean_object*, lean_object*, lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_security__by__construction_elim___redArg(lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_security__by__construction_elim___redArg___boxed(lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_security__by__construction_elim(lean_object*, uint8_t, lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_security__by__construction_elim___boxed(lean_object*, lean_object*, lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_idempotence_elim___redArg(lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_idempotence_elim___redArg___boxed(lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_idempotence_elim(lean_object*, uint8_t, lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_idempotence_elim___boxed(lean_object*, lean_object*, lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_concurrency__correctness_elim___redArg(lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_concurrency__correctness_elim___redArg___boxed(lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_concurrency__correctness_elim(lean_object*, uint8_t, lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_concurrency__correctness_elim___boxed(lean_object*, lean_object*, lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_observability_elim___redArg(lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_observability_elim___redArg___boxed(lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_observability_elim(lean_object*, uint8_t, lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_observability_elim___boxed(lean_object*, lean_object*, lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_testability__falsifiability_elim___redArg(lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_testability__falsifiability_elim___redArg___boxed(lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_testability__falsifiability_elim(lean_object*, uint8_t, lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_testability__falsifiability_elim___boxed(lean_object*, lean_object*, lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_change__locality_elim___redArg(lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_change__locality_elim___redArg___boxed(lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_change__locality_elim(lean_object*, uint8_t, lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_change__locality_elim___boxed(lean_object*, lean_object*, lean_object*, lean_object*);
LEAN_EXPORT uint8_t lp_keel_ExcellentCode_Atom_ofNat(lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_ofNat___boxed(lean_object*);
LEAN_EXPORT uint8_t lp_keel_ExcellentCode_instDecidableEqAtom(uint8_t, uint8_t);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_instDecidableEqAtom___boxed(lean_object*, lean_object*);
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_ctorIdx(uint8_t v_x_1_){
_start:
{
switch(v_x_1_)
{
case 0:
{
lean_object* v___x_2_; 
v___x_2_ = lean_unsigned_to_nat(0u);
return v___x_2_;
}
case 1:
{
lean_object* v___x_3_; 
v___x_3_ = lean_unsigned_to_nat(1u);
return v___x_3_;
}
case 2:
{
lean_object* v___x_4_; 
v___x_4_ = lean_unsigned_to_nat(2u);
return v___x_4_;
}
case 3:
{
lean_object* v___x_5_; 
v___x_5_ = lean_unsigned_to_nat(3u);
return v___x_5_;
}
case 4:
{
lean_object* v___x_6_; 
v___x_6_ = lean_unsigned_to_nat(4u);
return v___x_6_;
}
case 5:
{
lean_object* v___x_7_; 
v___x_7_ = lean_unsigned_to_nat(5u);
return v___x_7_;
}
case 6:
{
lean_object* v___x_8_; 
v___x_8_ = lean_unsigned_to_nat(6u);
return v___x_8_;
}
case 7:
{
lean_object* v___x_9_; 
v___x_9_ = lean_unsigned_to_nat(7u);
return v___x_9_;
}
case 8:
{
lean_object* v___x_10_; 
v___x_10_ = lean_unsigned_to_nat(8u);
return v___x_10_;
}
case 9:
{
lean_object* v___x_11_; 
v___x_11_ = lean_unsigned_to_nat(9u);
return v___x_11_;
}
case 10:
{
lean_object* v___x_12_; 
v___x_12_ = lean_unsigned_to_nat(10u);
return v___x_12_;
}
case 11:
{
lean_object* v___x_13_; 
v___x_13_ = lean_unsigned_to_nat(11u);
return v___x_13_;
}
case 12:
{
lean_object* v___x_14_; 
v___x_14_ = lean_unsigned_to_nat(12u);
return v___x_14_;
}
case 13:
{
lean_object* v___x_15_; 
v___x_15_ = lean_unsigned_to_nat(13u);
return v___x_15_;
}
case 14:
{
lean_object* v___x_16_; 
v___x_16_ = lean_unsigned_to_nat(14u);
return v___x_16_;
}
case 15:
{
lean_object* v___x_17_; 
v___x_17_ = lean_unsigned_to_nat(15u);
return v___x_17_;
}
case 16:
{
lean_object* v___x_18_; 
v___x_18_ = lean_unsigned_to_nat(16u);
return v___x_18_;
}
case 17:
{
lean_object* v___x_19_; 
v___x_19_ = lean_unsigned_to_nat(17u);
return v___x_19_;
}
case 18:
{
lean_object* v___x_20_; 
v___x_20_ = lean_unsigned_to_nat(18u);
return v___x_20_;
}
default: 
{
lean_object* v___x_21_; 
v___x_21_ = lean_unsigned_to_nat(19u);
return v___x_21_;
}
}
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_ctorIdx___boxed(lean_object* v_x_22_){
_start:
{
uint8_t v_x_boxed_23_; lean_object* v_res_24_; 
v_x_boxed_23_ = lean_unbox(v_x_22_);
v_res_24_ = lp_keel_ExcellentCode_Atom_ctorIdx(v_x_boxed_23_);
return v_res_24_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_toCtorIdx(uint8_t v_x_25_){
_start:
{
lean_object* v___x_26_; 
v___x_26_ = lp_keel_ExcellentCode_Atom_ctorIdx(v_x_25_);
return v___x_26_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_toCtorIdx___boxed(lean_object* v_x_27_){
_start:
{
uint8_t v_x_4__boxed_28_; lean_object* v_res_29_; 
v_x_4__boxed_28_ = lean_unbox(v_x_27_);
v_res_29_ = lp_keel_ExcellentCode_Atom_toCtorIdx(v_x_4__boxed_28_);
return v_res_29_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_ctorElim___redArg(lean_object* v_k_30_){
_start:
{
lean_inc(v_k_30_);
return v_k_30_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_ctorElim___redArg___boxed(lean_object* v_k_31_){
_start:
{
lean_object* v_res_32_; 
v_res_32_ = lp_keel_ExcellentCode_Atom_ctorElim___redArg(v_k_31_);
lean_dec(v_k_31_);
return v_res_32_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_ctorElim(lean_object* v_motive_33_, lean_object* v_ctorIdx_34_, uint8_t v_t_35_, lean_object* v_h_36_, lean_object* v_k_37_){
_start:
{
lean_inc(v_k_37_);
return v_k_37_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_ctorElim___boxed(lean_object* v_motive_38_, lean_object* v_ctorIdx_39_, lean_object* v_t_40_, lean_object* v_h_41_, lean_object* v_k_42_){
_start:
{
uint8_t v_t_boxed_43_; lean_object* v_res_44_; 
v_t_boxed_43_ = lean_unbox(v_t_40_);
v_res_44_ = lp_keel_ExcellentCode_Atom_ctorElim(v_motive_38_, v_ctorIdx_39_, v_t_boxed_43_, v_h_41_, v_k_42_);
lean_dec(v_k_42_);
lean_dec(v_ctorIdx_39_);
return v_res_44_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_referential__truth_elim___redArg(lean_object* v_referential__truth_45_){
_start:
{
lean_inc(v_referential__truth_45_);
return v_referential__truth_45_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_referential__truth_elim___redArg___boxed(lean_object* v_referential__truth_46_){
_start:
{
lean_object* v_res_47_; 
v_res_47_ = lp_keel_ExcellentCode_Atom_referential__truth_elim___redArg(v_referential__truth_46_);
lean_dec(v_referential__truth_46_);
return v_res_47_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_referential__truth_elim(lean_object* v_motive_48_, uint8_t v_t_49_, lean_object* v_h_50_, lean_object* v_referential__truth_51_){
_start:
{
lean_inc(v_referential__truth_51_);
return v_referential__truth_51_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_referential__truth_elim___boxed(lean_object* v_motive_52_, lean_object* v_t_53_, lean_object* v_h_54_, lean_object* v_referential__truth_55_){
_start:
{
uint8_t v_t_boxed_56_; lean_object* v_res_57_; 
v_t_boxed_56_ = lean_unbox(v_t_53_);
v_res_57_ = lp_keel_ExcellentCode_Atom_referential__truth_elim(v_motive_52_, v_t_boxed_56_, v_h_54_, v_referential__truth_55_);
lean_dec(v_referential__truth_55_);
return v_res_57_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_specification__fidelity_elim___redArg(lean_object* v_specification__fidelity_58_){
_start:
{
lean_inc(v_specification__fidelity_58_);
return v_specification__fidelity_58_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_specification__fidelity_elim___redArg___boxed(lean_object* v_specification__fidelity_59_){
_start:
{
lean_object* v_res_60_; 
v_res_60_ = lp_keel_ExcellentCode_Atom_specification__fidelity_elim___redArg(v_specification__fidelity_59_);
lean_dec(v_specification__fidelity_59_);
return v_res_60_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_specification__fidelity_elim(lean_object* v_motive_61_, uint8_t v_t_62_, lean_object* v_h_63_, lean_object* v_specification__fidelity_64_){
_start:
{
lean_inc(v_specification__fidelity_64_);
return v_specification__fidelity_64_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_specification__fidelity_elim___boxed(lean_object* v_motive_65_, lean_object* v_t_66_, lean_object* v_h_67_, lean_object* v_specification__fidelity_68_){
_start:
{
uint8_t v_t_boxed_69_; lean_object* v_res_70_; 
v_t_boxed_69_ = lean_unbox(v_t_66_);
v_res_70_ = lp_keel_ExcellentCode_Atom_specification__fidelity_elim(v_motive_65_, v_t_boxed_69_, v_h_67_, v_specification__fidelity_68_);
lean_dec(v_specification__fidelity_68_);
return v_res_70_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_type__soundness_elim___redArg(lean_object* v_type__soundness_71_){
_start:
{
lean_inc(v_type__soundness_71_);
return v_type__soundness_71_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_type__soundness_elim___redArg___boxed(lean_object* v_type__soundness_72_){
_start:
{
lean_object* v_res_73_; 
v_res_73_ = lp_keel_ExcellentCode_Atom_type__soundness_elim___redArg(v_type__soundness_72_);
lean_dec(v_type__soundness_72_);
return v_res_73_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_type__soundness_elim(lean_object* v_motive_74_, uint8_t v_t_75_, lean_object* v_h_76_, lean_object* v_type__soundness_77_){
_start:
{
lean_inc(v_type__soundness_77_);
return v_type__soundness_77_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_type__soundness_elim___boxed(lean_object* v_motive_78_, lean_object* v_t_79_, lean_object* v_h_80_, lean_object* v_type__soundness_81_){
_start:
{
uint8_t v_t_boxed_82_; lean_object* v_res_83_; 
v_t_boxed_82_ = lean_unbox(v_t_79_);
v_res_83_ = lp_keel_ExcellentCode_Atom_type__soundness_elim(v_motive_78_, v_t_boxed_82_, v_h_80_, v_type__soundness_81_);
lean_dec(v_type__soundness_81_);
return v_res_83_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_precondition__correctness_elim___redArg(lean_object* v_precondition__correctness_84_){
_start:
{
lean_inc(v_precondition__correctness_84_);
return v_precondition__correctness_84_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_precondition__correctness_elim___redArg___boxed(lean_object* v_precondition__correctness_85_){
_start:
{
lean_object* v_res_86_; 
v_res_86_ = lp_keel_ExcellentCode_Atom_precondition__correctness_elim___redArg(v_precondition__correctness_85_);
lean_dec(v_precondition__correctness_85_);
return v_res_86_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_precondition__correctness_elim(lean_object* v_motive_87_, uint8_t v_t_88_, lean_object* v_h_89_, lean_object* v_precondition__correctness_90_){
_start:
{
lean_inc(v_precondition__correctness_90_);
return v_precondition__correctness_90_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_precondition__correctness_elim___boxed(lean_object* v_motive_91_, lean_object* v_t_92_, lean_object* v_h_93_, lean_object* v_precondition__correctness_94_){
_start:
{
uint8_t v_t_boxed_95_; lean_object* v_res_96_; 
v_t_boxed_95_ = lean_unbox(v_t_92_);
v_res_96_ = lp_keel_ExcellentCode_Atom_precondition__correctness_elim(v_motive_91_, v_t_boxed_95_, v_h_93_, v_precondition__correctness_94_);
lean_dec(v_precondition__correctness_94_);
return v_res_96_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_postcondition__correctness_elim___redArg(lean_object* v_postcondition__correctness_97_){
_start:
{
lean_inc(v_postcondition__correctness_97_);
return v_postcondition__correctness_97_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_postcondition__correctness_elim___redArg___boxed(lean_object* v_postcondition__correctness_98_){
_start:
{
lean_object* v_res_99_; 
v_res_99_ = lp_keel_ExcellentCode_Atom_postcondition__correctness_elim___redArg(v_postcondition__correctness_98_);
lean_dec(v_postcondition__correctness_98_);
return v_res_99_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_postcondition__correctness_elim(lean_object* v_motive_100_, uint8_t v_t_101_, lean_object* v_h_102_, lean_object* v_postcondition__correctness_103_){
_start:
{
lean_inc(v_postcondition__correctness_103_);
return v_postcondition__correctness_103_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_postcondition__correctness_elim___boxed(lean_object* v_motive_104_, lean_object* v_t_105_, lean_object* v_h_106_, lean_object* v_postcondition__correctness_107_){
_start:
{
uint8_t v_t_boxed_108_; lean_object* v_res_109_; 
v_t_boxed_108_ = lean_unbox(v_t_105_);
v_res_109_ = lp_keel_ExcellentCode_Atom_postcondition__correctness_elim(v_motive_104_, v_t_boxed_108_, v_h_106_, v_postcondition__correctness_107_);
lean_dec(v_postcondition__correctness_107_);
return v_res_109_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_invariant__preservation_elim___redArg(lean_object* v_invariant__preservation_110_){
_start:
{
lean_inc(v_invariant__preservation_110_);
return v_invariant__preservation_110_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_invariant__preservation_elim___redArg___boxed(lean_object* v_invariant__preservation_111_){
_start:
{
lean_object* v_res_112_; 
v_res_112_ = lp_keel_ExcellentCode_Atom_invariant__preservation_elim___redArg(v_invariant__preservation_111_);
lean_dec(v_invariant__preservation_111_);
return v_res_112_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_invariant__preservation_elim(lean_object* v_motive_113_, uint8_t v_t_114_, lean_object* v_h_115_, lean_object* v_invariant__preservation_116_){
_start:
{
lean_inc(v_invariant__preservation_116_);
return v_invariant__preservation_116_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_invariant__preservation_elim___boxed(lean_object* v_motive_117_, lean_object* v_t_118_, lean_object* v_h_119_, lean_object* v_invariant__preservation_120_){
_start:
{
uint8_t v_t_boxed_121_; lean_object* v_res_122_; 
v_t_boxed_121_ = lean_unbox(v_t_118_);
v_res_122_ = lp_keel_ExcellentCode_Atom_invariant__preservation_elim(v_motive_117_, v_t_boxed_121_, v_h_119_, v_invariant__preservation_120_);
lean_dec(v_invariant__preservation_120_);
return v_res_122_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_totality__or__controlled__partiality_elim___redArg(lean_object* v_totality__or__controlled__partiality_123_){
_start:
{
lean_inc(v_totality__or__controlled__partiality_123_);
return v_totality__or__controlled__partiality_123_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_totality__or__controlled__partiality_elim___redArg___boxed(lean_object* v_totality__or__controlled__partiality_124_){
_start:
{
lean_object* v_res_125_; 
v_res_125_ = lp_keel_ExcellentCode_Atom_totality__or__controlled__partiality_elim___redArg(v_totality__or__controlled__partiality_124_);
lean_dec(v_totality__or__controlled__partiality_124_);
return v_res_125_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_totality__or__controlled__partiality_elim(lean_object* v_motive_126_, uint8_t v_t_127_, lean_object* v_h_128_, lean_object* v_totality__or__controlled__partiality_129_){
_start:
{
lean_inc(v_totality__or__controlled__partiality_129_);
return v_totality__or__controlled__partiality_129_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_totality__or__controlled__partiality_elim___boxed(lean_object* v_motive_130_, lean_object* v_t_131_, lean_object* v_h_132_, lean_object* v_totality__or__controlled__partiality_133_){
_start:
{
uint8_t v_t_boxed_134_; lean_object* v_res_135_; 
v_t_boxed_134_ = lean_unbox(v_t_131_);
v_res_135_ = lp_keel_ExcellentCode_Atom_totality__or__controlled__partiality_elim(v_motive_130_, v_t_boxed_134_, v_h_132_, v_totality__or__controlled__partiality_133_);
lean_dec(v_totality__or__controlled__partiality_133_);
return v_res_135_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_boundary__completeness_elim___redArg(lean_object* v_boundary__completeness_136_){
_start:
{
lean_inc(v_boundary__completeness_136_);
return v_boundary__completeness_136_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_boundary__completeness_elim___redArg___boxed(lean_object* v_boundary__completeness_137_){
_start:
{
lean_object* v_res_138_; 
v_res_138_ = lp_keel_ExcellentCode_Atom_boundary__completeness_elim___redArg(v_boundary__completeness_137_);
lean_dec(v_boundary__completeness_137_);
return v_res_138_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_boundary__completeness_elim(lean_object* v_motive_139_, uint8_t v_t_140_, lean_object* v_h_141_, lean_object* v_boundary__completeness_142_){
_start:
{
lean_inc(v_boundary__completeness_142_);
return v_boundary__completeness_142_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_boundary__completeness_elim___boxed(lean_object* v_motive_143_, lean_object* v_t_144_, lean_object* v_h_145_, lean_object* v_boundary__completeness_146_){
_start:
{
uint8_t v_t_boxed_147_; lean_object* v_res_148_; 
v_t_boxed_147_ = lean_unbox(v_t_144_);
v_res_148_ = lp_keel_ExcellentCode_Atom_boundary__completeness_elim(v_motive_143_, v_t_boxed_147_, v_h_145_, v_boundary__completeness_146_);
lean_dec(v_boundary__completeness_146_);
return v_res_148_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_compositionality_elim___redArg(lean_object* v_compositionality_149_){
_start:
{
lean_inc(v_compositionality_149_);
return v_compositionality_149_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_compositionality_elim___redArg___boxed(lean_object* v_compositionality_150_){
_start:
{
lean_object* v_res_151_; 
v_res_151_ = lp_keel_ExcellentCode_Atom_compositionality_elim___redArg(v_compositionality_150_);
lean_dec(v_compositionality_150_);
return v_res_151_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_compositionality_elim(lean_object* v_motive_152_, uint8_t v_t_153_, lean_object* v_h_154_, lean_object* v_compositionality_155_){
_start:
{
lean_inc(v_compositionality_155_);
return v_compositionality_155_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_compositionality_elim___boxed(lean_object* v_motive_156_, lean_object* v_t_157_, lean_object* v_h_158_, lean_object* v_compositionality_159_){
_start:
{
uint8_t v_t_boxed_160_; lean_object* v_res_161_; 
v_t_boxed_160_ = lean_unbox(v_t_157_);
v_res_161_ = lp_keel_ExcellentCode_Atom_compositionality_elim(v_motive_156_, v_t_boxed_160_, v_h_158_, v_compositionality_159_);
lean_dec(v_compositionality_159_);
return v_res_161_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_minimal__sufficient__complexity_elim___redArg(lean_object* v_minimal__sufficient__complexity_162_){
_start:
{
lean_inc(v_minimal__sufficient__complexity_162_);
return v_minimal__sufficient__complexity_162_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_minimal__sufficient__complexity_elim___redArg___boxed(lean_object* v_minimal__sufficient__complexity_163_){
_start:
{
lean_object* v_res_164_; 
v_res_164_ = lp_keel_ExcellentCode_Atom_minimal__sufficient__complexity_elim___redArg(v_minimal__sufficient__complexity_163_);
lean_dec(v_minimal__sufficient__complexity_163_);
return v_res_164_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_minimal__sufficient__complexity_elim(lean_object* v_motive_165_, uint8_t v_t_166_, lean_object* v_h_167_, lean_object* v_minimal__sufficient__complexity_168_){
_start:
{
lean_inc(v_minimal__sufficient__complexity_168_);
return v_minimal__sufficient__complexity_168_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_minimal__sufficient__complexity_elim___boxed(lean_object* v_motive_169_, lean_object* v_t_170_, lean_object* v_h_171_, lean_object* v_minimal__sufficient__complexity_172_){
_start:
{
uint8_t v_t_boxed_173_; lean_object* v_res_174_; 
v_t_boxed_173_ = lean_unbox(v_t_170_);
v_res_174_ = lp_keel_ExcellentCode_Atom_minimal__sufficient__complexity_elim(v_motive_169_, v_t_boxed_173_, v_h_171_, v_minimal__sufficient__complexity_172_);
lean_dec(v_minimal__sufficient__complexity_172_);
return v_res_174_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_algorithmic__efficiency_elim___redArg(lean_object* v_algorithmic__efficiency_175_){
_start:
{
lean_inc(v_algorithmic__efficiency_175_);
return v_algorithmic__efficiency_175_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_algorithmic__efficiency_elim___redArg___boxed(lean_object* v_algorithmic__efficiency_176_){
_start:
{
lean_object* v_res_177_; 
v_res_177_ = lp_keel_ExcellentCode_Atom_algorithmic__efficiency_elim___redArg(v_algorithmic__efficiency_176_);
lean_dec(v_algorithmic__efficiency_176_);
return v_res_177_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_algorithmic__efficiency_elim(lean_object* v_motive_178_, uint8_t v_t_179_, lean_object* v_h_180_, lean_object* v_algorithmic__efficiency_181_){
_start:
{
lean_inc(v_algorithmic__efficiency_181_);
return v_algorithmic__efficiency_181_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_algorithmic__efficiency_elim___boxed(lean_object* v_motive_182_, lean_object* v_t_183_, lean_object* v_h_184_, lean_object* v_algorithmic__efficiency_185_){
_start:
{
uint8_t v_t_boxed_186_; lean_object* v_res_187_; 
v_t_boxed_186_ = lean_unbox(v_t_183_);
v_res_187_ = lp_keel_ExcellentCode_Atom_algorithmic__efficiency_elim(v_motive_182_, v_t_boxed_186_, v_h_184_, v_algorithmic__efficiency_185_);
lean_dec(v_algorithmic__efficiency_185_);
return v_res_187_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_state__minimization_elim___redArg(lean_object* v_state__minimization_188_){
_start:
{
lean_inc(v_state__minimization_188_);
return v_state__minimization_188_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_state__minimization_elim___redArg___boxed(lean_object* v_state__minimization_189_){
_start:
{
lean_object* v_res_190_; 
v_res_190_ = lp_keel_ExcellentCode_Atom_state__minimization_elim___redArg(v_state__minimization_189_);
lean_dec(v_state__minimization_189_);
return v_res_190_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_state__minimization_elim(lean_object* v_motive_191_, uint8_t v_t_192_, lean_object* v_h_193_, lean_object* v_state__minimization_194_){
_start:
{
lean_inc(v_state__minimization_194_);
return v_state__minimization_194_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_state__minimization_elim___boxed(lean_object* v_motive_195_, lean_object* v_t_196_, lean_object* v_h_197_, lean_object* v_state__minimization_198_){
_start:
{
uint8_t v_t_boxed_199_; lean_object* v_res_200_; 
v_t_boxed_199_ = lean_unbox(v_t_196_);
v_res_200_ = lp_keel_ExcellentCode_Atom_state__minimization_elim(v_motive_195_, v_t_boxed_199_, v_h_197_, v_state__minimization_198_);
lean_dec(v_state__minimization_198_);
return v_res_200_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_data__model__truth_elim___redArg(lean_object* v_data__model__truth_201_){
_start:
{
lean_inc(v_data__model__truth_201_);
return v_data__model__truth_201_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_data__model__truth_elim___redArg___boxed(lean_object* v_data__model__truth_202_){
_start:
{
lean_object* v_res_203_; 
v_res_203_ = lp_keel_ExcellentCode_Atom_data__model__truth_elim___redArg(v_data__model__truth_202_);
lean_dec(v_data__model__truth_202_);
return v_res_203_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_data__model__truth_elim(lean_object* v_motive_204_, uint8_t v_t_205_, lean_object* v_h_206_, lean_object* v_data__model__truth_207_){
_start:
{
lean_inc(v_data__model__truth_207_);
return v_data__model__truth_207_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_data__model__truth_elim___boxed(lean_object* v_motive_208_, lean_object* v_t_209_, lean_object* v_h_210_, lean_object* v_data__model__truth_211_){
_start:
{
uint8_t v_t_boxed_212_; lean_object* v_res_213_; 
v_t_boxed_212_ = lean_unbox(v_t_209_);
v_res_213_ = lp_keel_ExcellentCode_Atom_data__model__truth_elim(v_motive_208_, v_t_boxed_212_, v_h_210_, v_data__model__truth_211_);
lean_dec(v_data__model__truth_211_);
return v_res_213_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_error__semantics_elim___redArg(lean_object* v_error__semantics_214_){
_start:
{
lean_inc(v_error__semantics_214_);
return v_error__semantics_214_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_error__semantics_elim___redArg___boxed(lean_object* v_error__semantics_215_){
_start:
{
lean_object* v_res_216_; 
v_res_216_ = lp_keel_ExcellentCode_Atom_error__semantics_elim___redArg(v_error__semantics_215_);
lean_dec(v_error__semantics_215_);
return v_res_216_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_error__semantics_elim(lean_object* v_motive_217_, uint8_t v_t_218_, lean_object* v_h_219_, lean_object* v_error__semantics_220_){
_start:
{
lean_inc(v_error__semantics_220_);
return v_error__semantics_220_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_error__semantics_elim___boxed(lean_object* v_motive_221_, lean_object* v_t_222_, lean_object* v_h_223_, lean_object* v_error__semantics_224_){
_start:
{
uint8_t v_t_boxed_225_; lean_object* v_res_226_; 
v_t_boxed_225_ = lean_unbox(v_t_222_);
v_res_226_ = lp_keel_ExcellentCode_Atom_error__semantics_elim(v_motive_221_, v_t_boxed_225_, v_h_223_, v_error__semantics_224_);
lean_dec(v_error__semantics_224_);
return v_res_226_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_security__by__construction_elim___redArg(lean_object* v_security__by__construction_227_){
_start:
{
lean_inc(v_security__by__construction_227_);
return v_security__by__construction_227_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_security__by__construction_elim___redArg___boxed(lean_object* v_security__by__construction_228_){
_start:
{
lean_object* v_res_229_; 
v_res_229_ = lp_keel_ExcellentCode_Atom_security__by__construction_elim___redArg(v_security__by__construction_228_);
lean_dec(v_security__by__construction_228_);
return v_res_229_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_security__by__construction_elim(lean_object* v_motive_230_, uint8_t v_t_231_, lean_object* v_h_232_, lean_object* v_security__by__construction_233_){
_start:
{
lean_inc(v_security__by__construction_233_);
return v_security__by__construction_233_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_security__by__construction_elim___boxed(lean_object* v_motive_234_, lean_object* v_t_235_, lean_object* v_h_236_, lean_object* v_security__by__construction_237_){
_start:
{
uint8_t v_t_boxed_238_; lean_object* v_res_239_; 
v_t_boxed_238_ = lean_unbox(v_t_235_);
v_res_239_ = lp_keel_ExcellentCode_Atom_security__by__construction_elim(v_motive_234_, v_t_boxed_238_, v_h_236_, v_security__by__construction_237_);
lean_dec(v_security__by__construction_237_);
return v_res_239_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_idempotence_elim___redArg(lean_object* v_idempotence_240_){
_start:
{
lean_inc(v_idempotence_240_);
return v_idempotence_240_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_idempotence_elim___redArg___boxed(lean_object* v_idempotence_241_){
_start:
{
lean_object* v_res_242_; 
v_res_242_ = lp_keel_ExcellentCode_Atom_idempotence_elim___redArg(v_idempotence_241_);
lean_dec(v_idempotence_241_);
return v_res_242_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_idempotence_elim(lean_object* v_motive_243_, uint8_t v_t_244_, lean_object* v_h_245_, lean_object* v_idempotence_246_){
_start:
{
lean_inc(v_idempotence_246_);
return v_idempotence_246_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_idempotence_elim___boxed(lean_object* v_motive_247_, lean_object* v_t_248_, lean_object* v_h_249_, lean_object* v_idempotence_250_){
_start:
{
uint8_t v_t_boxed_251_; lean_object* v_res_252_; 
v_t_boxed_251_ = lean_unbox(v_t_248_);
v_res_252_ = lp_keel_ExcellentCode_Atom_idempotence_elim(v_motive_247_, v_t_boxed_251_, v_h_249_, v_idempotence_250_);
lean_dec(v_idempotence_250_);
return v_res_252_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_concurrency__correctness_elim___redArg(lean_object* v_concurrency__correctness_253_){
_start:
{
lean_inc(v_concurrency__correctness_253_);
return v_concurrency__correctness_253_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_concurrency__correctness_elim___redArg___boxed(lean_object* v_concurrency__correctness_254_){
_start:
{
lean_object* v_res_255_; 
v_res_255_ = lp_keel_ExcellentCode_Atom_concurrency__correctness_elim___redArg(v_concurrency__correctness_254_);
lean_dec(v_concurrency__correctness_254_);
return v_res_255_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_concurrency__correctness_elim(lean_object* v_motive_256_, uint8_t v_t_257_, lean_object* v_h_258_, lean_object* v_concurrency__correctness_259_){
_start:
{
lean_inc(v_concurrency__correctness_259_);
return v_concurrency__correctness_259_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_concurrency__correctness_elim___boxed(lean_object* v_motive_260_, lean_object* v_t_261_, lean_object* v_h_262_, lean_object* v_concurrency__correctness_263_){
_start:
{
uint8_t v_t_boxed_264_; lean_object* v_res_265_; 
v_t_boxed_264_ = lean_unbox(v_t_261_);
v_res_265_ = lp_keel_ExcellentCode_Atom_concurrency__correctness_elim(v_motive_260_, v_t_boxed_264_, v_h_262_, v_concurrency__correctness_263_);
lean_dec(v_concurrency__correctness_263_);
return v_res_265_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_observability_elim___redArg(lean_object* v_observability_266_){
_start:
{
lean_inc(v_observability_266_);
return v_observability_266_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_observability_elim___redArg___boxed(lean_object* v_observability_267_){
_start:
{
lean_object* v_res_268_; 
v_res_268_ = lp_keel_ExcellentCode_Atom_observability_elim___redArg(v_observability_267_);
lean_dec(v_observability_267_);
return v_res_268_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_observability_elim(lean_object* v_motive_269_, uint8_t v_t_270_, lean_object* v_h_271_, lean_object* v_observability_272_){
_start:
{
lean_inc(v_observability_272_);
return v_observability_272_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_observability_elim___boxed(lean_object* v_motive_273_, lean_object* v_t_274_, lean_object* v_h_275_, lean_object* v_observability_276_){
_start:
{
uint8_t v_t_boxed_277_; lean_object* v_res_278_; 
v_t_boxed_277_ = lean_unbox(v_t_274_);
v_res_278_ = lp_keel_ExcellentCode_Atom_observability_elim(v_motive_273_, v_t_boxed_277_, v_h_275_, v_observability_276_);
lean_dec(v_observability_276_);
return v_res_278_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_testability__falsifiability_elim___redArg(lean_object* v_testability__falsifiability_279_){
_start:
{
lean_inc(v_testability__falsifiability_279_);
return v_testability__falsifiability_279_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_testability__falsifiability_elim___redArg___boxed(lean_object* v_testability__falsifiability_280_){
_start:
{
lean_object* v_res_281_; 
v_res_281_ = lp_keel_ExcellentCode_Atom_testability__falsifiability_elim___redArg(v_testability__falsifiability_280_);
lean_dec(v_testability__falsifiability_280_);
return v_res_281_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_testability__falsifiability_elim(lean_object* v_motive_282_, uint8_t v_t_283_, lean_object* v_h_284_, lean_object* v_testability__falsifiability_285_){
_start:
{
lean_inc(v_testability__falsifiability_285_);
return v_testability__falsifiability_285_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_testability__falsifiability_elim___boxed(lean_object* v_motive_286_, lean_object* v_t_287_, lean_object* v_h_288_, lean_object* v_testability__falsifiability_289_){
_start:
{
uint8_t v_t_boxed_290_; lean_object* v_res_291_; 
v_t_boxed_290_ = lean_unbox(v_t_287_);
v_res_291_ = lp_keel_ExcellentCode_Atom_testability__falsifiability_elim(v_motive_286_, v_t_boxed_290_, v_h_288_, v_testability__falsifiability_289_);
lean_dec(v_testability__falsifiability_289_);
return v_res_291_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_change__locality_elim___redArg(lean_object* v_change__locality_292_){
_start:
{
lean_inc(v_change__locality_292_);
return v_change__locality_292_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_change__locality_elim___redArg___boxed(lean_object* v_change__locality_293_){
_start:
{
lean_object* v_res_294_; 
v_res_294_ = lp_keel_ExcellentCode_Atom_change__locality_elim___redArg(v_change__locality_293_);
lean_dec(v_change__locality_293_);
return v_res_294_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_change__locality_elim(lean_object* v_motive_295_, uint8_t v_t_296_, lean_object* v_h_297_, lean_object* v_change__locality_298_){
_start:
{
lean_inc(v_change__locality_298_);
return v_change__locality_298_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_change__locality_elim___boxed(lean_object* v_motive_299_, lean_object* v_t_300_, lean_object* v_h_301_, lean_object* v_change__locality_302_){
_start:
{
uint8_t v_t_boxed_303_; lean_object* v_res_304_; 
v_t_boxed_303_ = lean_unbox(v_t_300_);
v_res_304_ = lp_keel_ExcellentCode_Atom_change__locality_elim(v_motive_299_, v_t_boxed_303_, v_h_301_, v_change__locality_302_);
lean_dec(v_change__locality_302_);
return v_res_304_;
}
}
LEAN_EXPORT uint8_t lp_keel_ExcellentCode_Atom_ofNat(lean_object* v_n_305_){
_start:
{
lean_object* v___x_306_; uint8_t v___x_307_; 
v___x_306_ = lean_unsigned_to_nat(9u);
v___x_307_ = lean_nat_dec_le(v_n_305_, v___x_306_);
if (v___x_307_ == 0)
{
lean_object* v___x_308_; uint8_t v___x_309_; 
v___x_308_ = lean_unsigned_to_nat(14u);
v___x_309_ = lean_nat_dec_le(v_n_305_, v___x_308_);
if (v___x_309_ == 0)
{
lean_object* v___x_310_; uint8_t v___x_311_; 
v___x_310_ = lean_unsigned_to_nat(16u);
v___x_311_ = lean_nat_dec_le(v_n_305_, v___x_310_);
if (v___x_311_ == 0)
{
lean_object* v___x_312_; uint8_t v___x_313_; 
v___x_312_ = lean_unsigned_to_nat(17u);
v___x_313_ = lean_nat_dec_le(v_n_305_, v___x_312_);
if (v___x_313_ == 0)
{
lean_object* v___x_314_; uint8_t v___x_315_; 
v___x_314_ = lean_unsigned_to_nat(18u);
v___x_315_ = lean_nat_dec_le(v_n_305_, v___x_314_);
if (v___x_315_ == 0)
{
uint8_t v___x_316_; 
v___x_316_ = 19;
return v___x_316_;
}
else
{
uint8_t v___x_317_; 
v___x_317_ = 18;
return v___x_317_;
}
}
else
{
uint8_t v___x_318_; 
v___x_318_ = 17;
return v___x_318_;
}
}
else
{
lean_object* v___x_319_; uint8_t v___x_320_; 
v___x_319_ = lean_unsigned_to_nat(15u);
v___x_320_ = lean_nat_dec_le(v_n_305_, v___x_319_);
if (v___x_320_ == 0)
{
uint8_t v___x_321_; 
v___x_321_ = 16;
return v___x_321_;
}
else
{
uint8_t v___x_322_; 
v___x_322_ = 15;
return v___x_322_;
}
}
}
else
{
lean_object* v___x_323_; uint8_t v___x_324_; 
v___x_323_ = lean_unsigned_to_nat(11u);
v___x_324_ = lean_nat_dec_le(v_n_305_, v___x_323_);
if (v___x_324_ == 0)
{
lean_object* v___x_325_; uint8_t v___x_326_; 
v___x_325_ = lean_unsigned_to_nat(12u);
v___x_326_ = lean_nat_dec_le(v_n_305_, v___x_325_);
if (v___x_326_ == 0)
{
lean_object* v___x_327_; uint8_t v___x_328_; 
v___x_327_ = lean_unsigned_to_nat(13u);
v___x_328_ = lean_nat_dec_le(v_n_305_, v___x_327_);
if (v___x_328_ == 0)
{
uint8_t v___x_329_; 
v___x_329_ = 14;
return v___x_329_;
}
else
{
uint8_t v___x_330_; 
v___x_330_ = 13;
return v___x_330_;
}
}
else
{
uint8_t v___x_331_; 
v___x_331_ = 12;
return v___x_331_;
}
}
else
{
lean_object* v___x_332_; uint8_t v___x_333_; 
v___x_332_ = lean_unsigned_to_nat(10u);
v___x_333_ = lean_nat_dec_le(v_n_305_, v___x_332_);
if (v___x_333_ == 0)
{
uint8_t v___x_334_; 
v___x_334_ = 11;
return v___x_334_;
}
else
{
uint8_t v___x_335_; 
v___x_335_ = 10;
return v___x_335_;
}
}
}
}
else
{
lean_object* v___x_336_; uint8_t v___x_337_; 
v___x_336_ = lean_unsigned_to_nat(4u);
v___x_337_ = lean_nat_dec_le(v_n_305_, v___x_336_);
if (v___x_337_ == 0)
{
lean_object* v___x_338_; uint8_t v___x_339_; 
v___x_338_ = lean_unsigned_to_nat(6u);
v___x_339_ = lean_nat_dec_le(v_n_305_, v___x_338_);
if (v___x_339_ == 0)
{
lean_object* v___x_340_; uint8_t v___x_341_; 
v___x_340_ = lean_unsigned_to_nat(7u);
v___x_341_ = lean_nat_dec_le(v_n_305_, v___x_340_);
if (v___x_341_ == 0)
{
lean_object* v___x_342_; uint8_t v___x_343_; 
v___x_342_ = lean_unsigned_to_nat(8u);
v___x_343_ = lean_nat_dec_le(v_n_305_, v___x_342_);
if (v___x_343_ == 0)
{
uint8_t v___x_344_; 
v___x_344_ = 9;
return v___x_344_;
}
else
{
uint8_t v___x_345_; 
v___x_345_ = 8;
return v___x_345_;
}
}
else
{
uint8_t v___x_346_; 
v___x_346_ = 7;
return v___x_346_;
}
}
else
{
lean_object* v___x_347_; uint8_t v___x_348_; 
v___x_347_ = lean_unsigned_to_nat(5u);
v___x_348_ = lean_nat_dec_le(v_n_305_, v___x_347_);
if (v___x_348_ == 0)
{
uint8_t v___x_349_; 
v___x_349_ = 6;
return v___x_349_;
}
else
{
uint8_t v___x_350_; 
v___x_350_ = 5;
return v___x_350_;
}
}
}
else
{
lean_object* v___x_351_; uint8_t v___x_352_; 
v___x_351_ = lean_unsigned_to_nat(1u);
v___x_352_ = lean_nat_dec_le(v_n_305_, v___x_351_);
if (v___x_352_ == 0)
{
lean_object* v___x_353_; uint8_t v___x_354_; 
v___x_353_ = lean_unsigned_to_nat(2u);
v___x_354_ = lean_nat_dec_le(v_n_305_, v___x_353_);
if (v___x_354_ == 0)
{
lean_object* v___x_355_; uint8_t v___x_356_; 
v___x_355_ = lean_unsigned_to_nat(3u);
v___x_356_ = lean_nat_dec_le(v_n_305_, v___x_355_);
if (v___x_356_ == 0)
{
uint8_t v___x_357_; 
v___x_357_ = 4;
return v___x_357_;
}
else
{
uint8_t v___x_358_; 
v___x_358_ = 3;
return v___x_358_;
}
}
else
{
uint8_t v___x_359_; 
v___x_359_ = 2;
return v___x_359_;
}
}
else
{
lean_object* v___x_360_; uint8_t v___x_361_; 
v___x_360_ = lean_unsigned_to_nat(0u);
v___x_361_ = lean_nat_dec_le(v_n_305_, v___x_360_);
if (v___x_361_ == 0)
{
uint8_t v___x_362_; 
v___x_362_ = 1;
return v___x_362_;
}
else
{
uint8_t v___x_363_; 
v___x_363_ = 0;
return v___x_363_;
}
}
}
}
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_Atom_ofNat___boxed(lean_object* v_n_364_){
_start:
{
uint8_t v_res_365_; lean_object* v_r_366_; 
v_res_365_ = lp_keel_ExcellentCode_Atom_ofNat(v_n_364_);
lean_dec(v_n_364_);
v_r_366_ = lean_box(v_res_365_);
return v_r_366_;
}
}
LEAN_EXPORT uint8_t lp_keel_ExcellentCode_instDecidableEqAtom(uint8_t v_x_367_, uint8_t v_y_368_){
_start:
{
lean_object* v___x_369_; lean_object* v___x_370_; uint8_t v___x_371_; 
v___x_369_ = lp_keel_ExcellentCode_Atom_ctorIdx(v_x_367_);
v___x_370_ = lp_keel_ExcellentCode_Atom_ctorIdx(v_y_368_);
v___x_371_ = lean_nat_dec_eq(v___x_369_, v___x_370_);
lean_dec(v___x_370_);
lean_dec(v___x_369_);
return v___x_371_;
}
}
LEAN_EXPORT lean_object* lp_keel_ExcellentCode_instDecidableEqAtom___boxed(lean_object* v_x_372_, lean_object* v_y_373_){
_start:
{
uint8_t v_x_13__boxed_374_; uint8_t v_y_14__boxed_375_; uint8_t v_res_376_; lean_object* v_r_377_; 
v_x_13__boxed_374_ = lean_unbox(v_x_372_);
v_y_14__boxed_375_ = lean_unbox(v_y_373_);
v_res_376_ = lp_keel_ExcellentCode_instDecidableEqAtom(v_x_13__boxed_374_, v_y_14__boxed_375_);
v_r_377_ = lean_box(v_res_376_);
return v_r_377_;
}
}
lean_object* initialize_Init(uint8_t builtin);
lean_object* initialize_Init(uint8_t builtin);
static bool _G_initialized = false;
LEAN_EXPORT lean_object* initialize_keel_ExcellentCode_Framework(uint8_t builtin) {
lean_object * res;
if (_G_initialized) return lean_io_result_mk_ok(lean_box(0));
_G_initialized = true;
res = initialize_Init(builtin);
if (lean_io_result_is_error(res)) return res;
lean_dec_ref(res);
res = initialize_Init(builtin);
if (lean_io_result_is_error(res)) return res;
lean_dec_ref(res);
return lean_io_result_mk_ok(lean_box(0));
}
#ifdef __cplusplus
}
#endif
